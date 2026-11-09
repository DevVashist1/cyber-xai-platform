import os
import glob
import pandas as pd

INTERMEDIATE_DIR = "data/intermediate/cert"
LDAP_DIR = "data/raw/Cert/r4.2/LDAP"
OUT_MERGED = "data/intermediate/cert/merged_with_ldap.parquet"

def run_merge_and_ldap():
    print("=== STEP 4.4: OUTER JOINING 5 DAILY PARQUET TABLES ===")
    files = [
        "agg_logon.parquet",
        "agg_device.parquet",
        "agg_file.parquet",
        "agg_email.parquet",
        "agg_http.parquet"
    ]
    
    dfs = []
    for fname in files:
        fpath = os.path.join(INTERMEDIATE_DIR, fname)
        df = pd.read_parquet(fpath)
        df["date"] = pd.to_datetime(df["date"]).dt.date
        print(f"   Loaded {fname:<20} -> {len(df):>7,} rows | Cols: {list(df.columns)}")
        dfs.append(df)

    # Outer join across all 5 tables on (user_id, date)
    merged = dfs[0]
    for df_next in dfs[1:]:
        merged = pd.merge(merged, df_next, on=["user_id", "date"], how="outer")

    # Fill NaN with 0 for every numeric column automatically
    num_cols = [c for c in merged.columns if c not in ("user_id", "date")]
    for col in num_cols:
        if "bytes" in col:
            merged[col] = merged[col].fillna(0).astype("int64")
        else:
            merged[col] = merged[col].fillna(0).astype("int32")

    print(f"\n   -> Outer Join Complete! Total (user_id, date) rows: {len(merged):,}")
    print(f"   -> Unique Users after Outer Join: {merged['user_id'].nunique():,}")

    print("\n=== STEP 4.5: ATTACHING LDAP DEPARTMENT METADATA (WITH FALLBACK) ===")
    ldap_files = sorted(glob.glob(os.path.join(LDAP_DIR, "*.csv")))
    print(f"   Found {len(ldap_files)} monthly LDAP files in {LDAP_DIR}")

    ldap_list = [
        pd.read_csv(f, usecols=["user_id", "department", "functional_unit", "role"])
        for f in ldap_files
    ]
    df_ldap_all = pd.concat(ldap_list, ignore_index=True)

    # Fix: If 'department' is NaN in LDAP, fall back to 'functional_unit', then 'role'
    df_ldap_all["department"] = (
        df_ldap_all["department"]
        .fillna(df_ldap_all["functional_unit"])
        .fillna(df_ldap_all["role"])
    )
    
    # Drop rows where department is still NaN before deduplicating per user_id
    df_ldap = (
        df_ldap_all.dropna(subset=["department"])
        .drop_duplicates(subset=["user_id"], keep="last")
    )

    merged = pd.merge(merged, df_ldap[["user_id", "department"]], on="user_id", how="left")
    unassigned_dept = int(merged["department"].isna().sum())
    merged["department"] = merged["department"].fillna("Unknown")

    merged.sort_values(["user_id", "date"], inplace=True)
    merged.reset_index(drop=True, inplace=True)
    merged.to_parquet(OUT_MERGED, engine="pyarrow", index=False)

    print("\n--- SANITY CHECK: STEP 4.4 & 4.5 ---")
    print(f"Saved Intermediate File : {OUT_MERGED}")
    print(f"Total Rows              : {len(merged):,}")
    print(f"Unique Users            : {merged['user_id'].nunique():,}")
    print(f"Date Range              : {merged['date'].min()} -> {merged['date'].max()}")
    print(f"Unassigned Departments  : {unassigned_dept} (Should be 0!)")
    print(f"Unique Departments ({merged['department'].nunique()}): {merged['department'].unique().tolist()}")
    print("\nFirst 5 rows:")
    print(merged.head(5))

if __name__ == "__main__":
    run_merge_and_ldap()