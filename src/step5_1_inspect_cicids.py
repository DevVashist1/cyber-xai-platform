import os
import glob
import pandas as pd
import numpy as np

CICIDS_DIR = "data/raw/CICIDS/GeneratedLabelledFlows/TrafficLabelling_"

def inspect_cicids():
    print("=== STEP 5.1: CICIDS2017 RAW FILES DIAGNOSTIC ===\n")
    csv_files = sorted(glob.glob(os.path.join(CICIDS_DIR, "*.csv")))
    
    if not csv_files:
        print(f"[!] No CSV files found in {CICIDS_DIR}")
        return

    total_raw_rows = 0
    all_labels = {}

    for idx, fpath in enumerate(csv_files, 1):
        fname = os.path.basename(fpath)
        size_mb = os.path.getsize(fpath) / (1024 * 1024)
        source_day = fname.split("-")[0].strip()
        
        print(f"[{idx}/8] File: {fname} ({size_mb:.2f} MB) | source_day='{source_day}'")
        
        # Read file (one file at a time fits easily in 8GB RAM)
        df = pd.read_csv(fpath, encoding_errors="replace", low_memory=False)
        rows = len(df)
        total_raw_rows += rows
        
        # Check column whitespace defect (Step 5.2)
        spaced_cols = [c for c in df.columns if c != c.strip()]
        
        # Strip columns temporarily just to inspect Label and Timestamp
        df.columns = [c.strip() for c in df.columns]
        
        # Check fully blank rows vs Infinity/NaN rows
        fully_blank_rows = int(df.isna().all(axis=1).sum())
        num_cols = df.select_dtypes(include=[np.number]).columns
        inf_count = int(np.isinf(df[num_cols]).values.sum())
        nan_rows = int(df.isna().any(axis=1).sum())
        
        # Check Timestamp sample
        ts_sample = df["Timestamp"].dropna().iloc[0] if "Timestamp" in df.columns and not df["Timestamp"].dropna().empty else "N/A"
        
        # Count attack labels
        if "Label" in df.columns:
            vc = df["Label"].dropna().value_counts().to_dict()
            for k, v in vc.items():
                all_labels[k] = all_labels.get(k, 0) + v
        else:
            vc = {}

        print(f"      Raw Rows           : {rows:,}")
        print(f"      Cols with spaces   : {len(spaced_cols)} / {len(df.columns)} (e.g., {spaced_cols[:3]})")
        print(f"      Fully blank rows   : {fully_blank_rows:,}")
        print(f"      Rows with any NaN  : {nan_rows:,} | Infinity cells: {inf_count:,}")
        print(f"      Timestamp sample   : '{ts_sample}'")
        print(f"      Labels in file     : {vc}\n")
        
        # Free memory before loading next file
        del df

    print("="*65)
    print(f"TOTAL RAW ROWS ACROSS ALL 8 FILES: {total_raw_rows:,}")
    print("COMBINED ATTACK LABEL COUNTS ACROSS DATASET:")
    for label, count in sorted(all_labels.items(), key=lambda x: x[1], reverse=True):
        print(f"  {label:<35} : {count:,}")
    print("="*65)

if __name__ == "__main__":
    inspect_cicids()