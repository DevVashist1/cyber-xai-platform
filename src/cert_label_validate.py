import pandas as pd

MERGED_PARQUET = "data/intermediate/cert/merged_with_ldap.parquet"
INSIDERS_CSV = "data/raw/Cert/answers/insiders.csv"
FINAL_PARQUET = "data/intermediate/user_daily_activity.parquet"

def run_label_and_validate():
    print("=== STEP 4.6: APPLYING TIME-SCOPED MALICIOUS LABELS ===")
    df = pd.read_parquet(MERGED_PARQUET)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["is_malicious"] = 0

    df_ans = pd.read_csv(INSIDERS_CSV)
    df_ans_42 = df_ans[df_ans["dataset"].astype(str).str.strip() == "4.2"].copy()
    
    df_ans_42["start_date"] = pd.to_datetime(df_ans_42["start"], errors="raise").dt.date
    df_ans_42["end_date"] = pd.to_datetime(df_ans_42["end"], errors="raise").dt.date

    for _, row in df_ans_42.iterrows():
        u_id = row["user"]
        s_date = row["start_date"]
        e_date = row["end_date"]
        
        # CRITICAL (Step 4.6): Mark is_malicious = 1 ONLY within [s_date, e_date]
        mask = (df["user_id"] == u_id) & (df["date"] >= s_date) & (df["date"] <= e_date)
        df.loc[mask, "is_malicious"] = 1

    df["is_malicious"] = df["is_malicious"].astype("int16")

    # Sort strictly by (user_id, date) before assigning row_id
    df = df.sort_values(["user_id", "date"]).reset_index(drop=True)

    # Section C Addendum: row_id surrogate primary key (needed by Django unmanaged model)
    df.insert(0, "row_id", df.index.values.astype("int64") + 1)

    # Section C Addendum: Exactly 15 final columns matching schema contract
    final_cols = [
        "row_id", "user_id", "date", "department",
        "logon_count", "after_hours_logons", "distinct_pcs",
        "usb_connects", "after_hours_usb_connects",
        "files_copied", "emails_sent", "external_emails", "emails_with_attachments",
        "websites_visited", "is_malicious"
    ]
    df = df[final_cols]

    df.to_parquet(FINAL_PARQUET, engine="pyarrow", index=False)

    # =========================================================================
    # STEP 4.7 & ADDENDUM E: VALIDATION TESTS D-01 TO D-07
    # =========================================================================
    count_cols = [
        "logon_count", "after_hours_logons", "distinct_pcs", "usb_connects",
        "after_hours_usb_connects", "files_copied", "emails_sent",
        "external_emails", "emails_with_attachments", "websites_visited"
    ]
    dup_keys = int(df.duplicated(subset=["user_id", "date"]).sum())
    neg_counts = int((df[count_cols] < 0).any().any())
    unknown_depts = int((df["department"] == "Unknown").sum())
    mal_rows = int(df["is_malicious"].sum())
    mal_users_active = df.loc[df["is_malicious"] == 1, "user_id"].nunique()
    total_days_of_mal_users = int(df["user_id"].isin(df_ans_42["user"]).sum())

    print("\n" + "="*70)
    print("STEP 4.7 & ADDENDUM E: CERT PIPELINE A VALIDATION REPORT (D-01 TO D-07)")
    print("="*70)
    print(f"Saved Final Parquet               : {FINAL_PARQUET}")
    print(f"Total Rows (user, date)           : {len(df):,}")
    print(f"Unique Users                      : {df['user_id'].nunique():,}")
    print(f"Date Range (D-07)                 : {df['date'].min()} -> {df['date'].max()}")
    print(f"D-02: Duplicate (user, date) Keys : {dup_keys} (Pass Condition: 0)")
    print(f"D-03: Negative Count Values       : {neg_counts} (Pass Condition: 0)")
    print(f"D-06: Users with No Department    : {unknown_depts} (Pass Condition: 0)")
    print(f"D-05: Malicious User-Days Rate    : {mal_rows:,} / {len(df):,} ({100*mal_rows/len(df):.3f}%)")
    print(f"      Malicious Insiders in r4.2  : {len(df_ans_42)} users (Active: {mal_users_active})")
    print(f"      Normal Days of Insiders Kept: {total_days_of_mal_users - mal_rows:,} user-days preserved as normal")
    print(f"Final Columns ({len(df.columns)})               : {list(df.columns)}")
    print("="*70)

    # D-04: Spot-check 5 known insiders against answers data
    print("\n--- D-04: SPOT-CHECKING 5 KNOWN INSIDERS (ATTACK WINDOW INTEGRITY) ---")
    insiders_to_check = df_ans_42.head(5)["user"].tolist()
    all_d04_passed = True

    for u_id in insiders_to_check:
        row_info = df_ans_42[df_ans_42["user"] == u_id].iloc[0]
        s_date, e_date = row_info["start_date"], row_info["end_date"]
        u_slice = df[df["user_id"] == u_id]

        inside_window = u_slice[(u_slice["date"] >= s_date) & (u_slice["date"] <= e_date)]
        outside_window = u_slice[(u_slice["date"] < s_date) | (u_slice["date"] > e_date)]

        inside_all_1 = (inside_window["is_malicious"] == 1).all() if not inside_window.empty else True
        outside_all_0 = (outside_window["is_malicious"] == 0).all() if not outside_window.empty else True
        passed = inside_all_1 and outside_all_0

        status = "PASSED" if passed else "FAILED"
        if not passed:
            all_d04_passed = False
        print(f"  [{status}] Insider {u_id:<8} | Window: {s_date} to {e_date} | Malicious Days: {inside_window['is_malicious'].sum():>2} | Normal Days: {len(outside_window):>3}")

    print(f"\nD-04 Overall Status: {'ALL 5 INSIDER WINDOWS VERIFIED PERFECTLY!' if all_d04_passed else 'SPOT-CHECK FAILED'}\n")

if __name__ == "__main__":
    run_label_and_validate()