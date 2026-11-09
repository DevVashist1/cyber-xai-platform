"""
Fast Update and Reload Script.
Regenerates CERT intermediate files with all amended columns:
- row_id (PK)
- distinct_pcs
- after_hours_usb_connects
- external_emails
- emails_with_attachments
And adds row_id to network_flows_clean, then reloads into PostgreSQL.
"""

import os
import time
import numpy as np
import pyarrow.parquet as pq

def main():
    t0 = time.time()
    print("=" * 75)
    print("STARTING FAST SCHEMA UPDATE & POSTGRES RELOAD")
    print("=" * 75)

    # 1. Regenerate CERT aggregations
    print("\n[1/6] Running logon_agg.py (distinct_pcs & Global Window 07:00-19:00)...")
    from logon_agg import run_logon_aggregation
    run_logon_aggregation()

    print("\n[2/6] Running device_agg.py (after_hours_usb_connects)...")
    from device_agg import run_device_agg
    run_device_agg()

    print("\n[3/6] Running email_agg.py (external_emails & emails_with_attachments)...")
    from email_agg import run_email_agg
    run_email_agg()

    print("\n[4/6] Running cert_merge_ldap.py (Outer join & LDAP fallback)...")
    from cert_merge_ldap import run_merge_and_ldap
    run_merge_and_ldap()

    print("\n[5/6] Running cert_label_validate.py (Adding row_id & 15 Section C columns)...")
    from cert_label_validate import run_label_and_validate
    run_label_and_validate()

    # 6. Ensure row_id in network_flows_clean.parquet
    print("\n[6/6] Ensuring row_id PK in network_flows_clean.parquet...")
    net_parquet = "data/intermediate/network_flows_clean.parquet"
    if os.path.exists(net_parquet):
        schema = pq.read_schema(net_parquet)
        if "row_id" not in schema.names:
            print("   -> Adding row_id column to network_flows_clean.parquet...")
            df_net = pq.read_table(net_parquet).to_pandas()
            df_net.insert(0, "row_id", np.arange(1, len(df_net) + 1, dtype=np.int64))
            df_net.to_parquet(net_parquet, engine="pyarrow", index=False)
            print("   -> row_id added successfully!")
        else:
            print("   -> row_id already present in network_flows_clean.parquet [OK]")

    # 7. Reload into PostgreSQL and build primary keys & indexes
    print("\n" + "=" * 75)
    print("RELOADING TABLES INTO POSTGRESQL 15 WITH CONSTRAINTS & INDEXES")
    print("=" * 75)
    from load_to_postgres import stream_parquet_to_postgres, build_indexes_and_verify, CERT_PARQUET, CICIDS_PARQUET
    stream_parquet_to_postgres(CERT_PARQUET, "user_daily_activity", batch_size=100_000)
    stream_parquet_to_postgres(CICIDS_PARQUET, "network_flows_clean", batch_size=100_000)
    build_indexes_and_verify()

    # 8. Run automatic schema verification
    print("\n" + "=" * 75)
    print("RUNNING FINAL SCHEMA & CONSTRAINT VERIFICATION")
    print("=" * 75)
    from verify_schema_and_pipeline import check_parquet_schema, check_postgres_schema
    p_ok = check_parquet_schema()
    db_ok = check_postgres_schema()

    elapsed = time.time() - t0
    print("\n" + "=" * 75)
    if p_ok and db_ok:
        print(f"SUCCESS! All schema amendments are 100% verified in {elapsed:.1f}s.")
        print("Both tables in Postgres have row_id PK, all 15 columns, constraints, and indexes.")
    else:
        print(f"Finished in {elapsed:.1f}s. Please check any messages above.")
    print("=" * 75)

if __name__ == "__main__":
    main()
