import os
import glob
import pandas as pd
import numpy as np

CICIDS_DIR = "data/raw/CICIDS/GeneratedLabelledFlows/TrafficLabelling_"
OUT_PARQUET = "data/intermediate/network_flows_clean.parquet"
os.makedirs("data/intermediate", exist_ok=True)

# Step 5.3: Explicitly exclude ultra-rare classes (< 50 samples across 2.8M rows)
RARE_CLASSES_TO_EXCLUDE = {
    "Heartbleed",
    "Web Attack - Sql Injection",
    "Infiltration"
}

# Step 5.3: Documented, consistent numeric mapping for surviving classes
LABEL_ENCODING_MAP = {
    "BENIGN": 0,
    "DoS Hulk": 1,
    "PortScan": 2,
    "DDoS": 3,
    "DoS GoldenEye": 4,
    "FTP-Patator": 5,
    "SSH-Patator": 6,
    "DoS slowloris": 7,
    "DoS Slowhttptest": 8,
    "Bot": 9,
    "Web Attack - Brute Force": 10,
    "Web Attack - XSS": 11
}

def clean_all_cicids():
    print("=== RUNNING PIPELINE B: STEPS 5.1 TO 5.5 ===\n")
    csv_files = sorted(glob.glob(os.path.join(CICIDS_DIR, "*.csv")))
    
    cleaned_chunks = []
    total_raw = 0
    total_dropped_nan_inf = 0
    total_dropped_dups = 0
    total_dropped_rare = 0

    for idx, fpath in enumerate(csv_files, 1):
        fname = os.path.basename(fpath)
        # Step 5.1: Preserve source_day from filename (e.g. 'Monday', 'Friday-Afternoon-DDos')
        source_day = fname.replace(".pcap_ISCX.csv", "").replace("-WorkingHours", "").replace("-workingHours", "")
        print(f"[{idx}/8] Processing {fname} (source_day='{source_day}')...")
        
        df = pd.read_csv(fpath, encoding_errors="replace", low_memory=False)
        raw_len = len(df)
        total_raw += raw_len

        # Step 5.2a: Strip leading/trailing whitespace from all column names
        df.columns = [c.strip() for c in df.columns]

        # Drop the string 'Flow ID' column so it doesn't collide with our integer flow_id
        if "Flow ID" in df.columns:
            df.drop(columns=["Flow ID"], inplace=True)

        # Step 5.2b: Replace Infinity with NaN, then drop all NaN/blank rows
        df.replace([np.inf, -np.inf], np.nan, inplace=True)
        after_nan_df = df.dropna().copy()
        dropped_nan = raw_len - len(after_nan_df)
        total_dropped_nan_inf += dropped_nan
        del df

        # Step 5.4: Remove duplicate rows BEFORE adding source_day/flow_id
        before_dup = len(after_nan_df)
        after_nan_df.drop_duplicates(inplace=True)
        dropped_dup = before_dup - len(after_nan_df)
        total_dropped_dups += dropped_dup

        # Step 5.3: Clean corrupted dash character in Label and filter rare classes
        after_nan_df["Label"] = (
            after_nan_df["Label"]
            .astype(str)
            .str.replace(r"[^\x00-\x7F]+", "-", regex=True)
            .str.replace(r"\s+", " ", regex=True)
            .str.strip()
        )
        before_rare = len(after_nan_df)
        after_nan_df = after_nan_df[~after_nan_df["Label"].isin(RARE_CLASSES_TO_EXCLUDE)].copy()
        total_dropped_rare += (before_rare - len(after_nan_df))

        # Map numeric label
        after_nan_df["attack_label_encoded"] = after_nan_df["Label"].map(LABEL_ENCODING_MAP).astype("int16")
        after_nan_df["source_day"] = source_day

        # Step 5.5: Parse Timestamp accurately
        # CICIDS2017 timestamps are DD/MM/YYYY HH:MM or DD/MM/YYYY HH:MM:SS
        after_nan_df["Timestamp"] = pd.to_datetime(
            after_nan_df["Timestamp"], format="mixed", dayfirst=True, errors="coerce"
        )
        after_nan_df.dropna(subset=["Timestamp"], inplace=True)

        # Downcast float64/int64 to float32/int32 so 2.5M rows fit easily in 8GB RAM
        for col in after_nan_df.select_dtypes(include=["float64"]).columns:
            after_nan_df[col] = after_nan_df[col].astype("float32")
        for col in after_nan_df.select_dtypes(include=["int64"]).columns:
            after_nan_df[col] = after_nan_df[col].astype("int32")

        print(f"      Kept {len(after_nan_df):,} rows (Dropped NaN/Inf: {dropped_nan:,} | Dups: {dropped_dup:,})")
        cleaned_chunks.append(after_nan_df)

    print("\nCombining all 8 cleaned tables into one dataset...")
    df_full = pd.concat(cleaned_chunks, ignore_index=True)
    del cleaned_chunks

    # Step 5.4 (Global Check): Drop any cross-file duplicates
    before_global_dup = len(df_full)
    df_full.drop_duplicates(inplace=True)
    total_dropped_dups += (before_global_dup - len(df_full))

    # Rename core columns to match Section 6 Postgres Schema
    rename_map = {
        "Timestamp": "timestamp",
        "Source IP": "src_ip",
        "Destination IP": "dst_ip",
        "Flow Duration": "duration",
        "Total Fwd Packets": "packet_count",
        "Total Length of Fwd Packets": "byte_count",
        "Label": "attack_label"
    }
    df_full.rename(columns=rename_map, inplace=True)

    # Normalize all remaining column names to clean Postgres snake_case
    df_full.columns = [
        c.lower().replace(" ", "_").replace("/", "_").replace(".", "_").replace("-", "_")
        for c in df_full.columns
    ]

    # Step 5.5: Sort chronologically by timestamp across entire 5-day capture
    print("Sorting all flows chronologically by timestamp (Step 5.5)...")
    df_full.sort_values("timestamp", inplace=True)
    df_full.reset_index(drop=True, inplace=True)

    # Section C Addendum: row_id surrogate primary key + flow_id
    df_full.insert(0, "flow_id", np.arange(1, len(df_full) + 1, dtype=np.int32))
    df_full.insert(0, "row_id", np.arange(1, len(df_full) + 1, dtype=np.int64))

    print(f"Saving final Parquet to {OUT_PARQUET}...")
    df_full.to_parquet(OUT_PARQUET, engine="pyarrow", index=False)

    print("\n" + "="*65)
    print("PIPELINE B (CICIDS2017) FINAL VALIDATION SUMMARY")
    print("="*65)
    print(f"Total Raw Rows Read          : {total_raw:,}")
    print(f"Dropped Blank / NaN / Inf    : {total_dropped_nan_inf:,}")
    print(f"Dropped Duplicate Rows       : {total_dropped_dups:,}")
    print(f"Excluded Rare Attack Rows    : {total_dropped_rare:,} ({RARE_CLASSES_TO_EXCLUDE})")
    print(f"FINAL CLEAN ROW COUNT        : {len(df_full):,}")
    print(f"Time Range                   : {df_full['timestamp'].min()} -> {df_full['timestamp'].max()}")
    print(f"Remaining NaN or Inf Count   : {int(df_full.isna().sum().sum())}")
    print("\nFinal Attack Label Breakdown:")
    print(df_full[["attack_label", "attack_label_encoded"]].value_counts())
    print("="*65)

if __name__ == "__main__":
    clean_all_cicids()