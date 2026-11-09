import os
import pandas as pd

RAW_FILE = "data/raw/Cert/r4.2/file.csv"
OUT_PARQUET = "data/intermediate/cert/agg_file.parquet"
os.makedirs(os.path.dirname(OUT_PARQUET), exist_ok=True)

def run_file_agg():
    print("\n=== STEP 4.3c: AGGREGATING file.csv (FULL FILE) ===")
    
    # Skip 'content' and 'filename' to save RAM and run 10x faster
    df = pd.read_csv(RAW_FILE, usecols=["id", "date", "user"])
    print(f"1. Total raw file events read : {len(df):,}")

    dt = pd.to_datetime(df["date"], format="%m/%d/%Y %H:%M:%S", errors="raise")
    df["date"] = dt.dt.date

    df_agg = df.groupby(["user", "date"], as_index=False).agg(
        files_copied=("id", "count")
    )
    df_agg.rename(columns={"user": "user_id"}, inplace=True)
    df_agg["files_copied"] = df_agg["files_copied"].astype("int32")
    df_agg.sort_values(["user_id", "date"], inplace=True)

    df_agg.to_parquet(OUT_PARQUET, engine="pyarrow", index=False)

    print("\n--- SANITY CHECK: agg_file.parquet ---")
    print(f"Total (user, date)  : {len(df_agg):,}")
    print(f"Unique File Users   : {df_agg['user_id'].nunique():,}")
    print(f"Date Range          : {df_agg['date'].min()} -> {df_agg['date'].max()}")
    print(f"Total Files Sum     : {df_agg['files_copied'].sum():,}")
    print(df_agg.head(5))

if __name__ == "__main__":
    run_file_agg()