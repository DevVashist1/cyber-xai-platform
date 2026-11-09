"""
Master Pipeline Orchestrator — Cyber XAI Platform (Module 1)
Runs the full data ingestion, cleaning, aggregation, labeling, and PostgreSQL streaming pipelines.
Ensures zero-intervention end-to-end execution.
"""

import sys
import time

def print_banner(step_num, title):
    print("\n" + "=" * 75)
    print(f"STEP {step_num}: {title.upper()}")
    print("=" * 75)

def main():
    t_start = time.time()
    print("=" * 75)
    print("STARTING END-TO-END DATA INGESTION & PREPROCESSING (MODULE 1)")
    print("=" * 75)

    # 1. Environment & Database Checkpoint
    print_banner(1, "Postgres Connection Checkpoint")
    from verify_setup import run_checkpoint
    run_checkpoint()

    # 2. Pipeline B: CICIDS2017 Cleaning & Staging
    print_banner(2, "Cleaning CICIDS2017 Network Dataset (Pipeline B)")
    from step5_clean_cicids import clean_all_cicids
    clean_all_cicids()

    # 3. Pipeline A: 5 Independent CERT Aggregations
    print_banner("3a", "Aggregating logon.csv (Working Hours & distinct_pcs)")
    from logon_agg import run_logon_aggregation
    run_logon_aggregation()

    print_banner("3b", "Aggregating device.csv (usb_connects & after_hours_usb)")
    from device_agg import run_device_agg
    run_device_agg()

    print_banner("3c", "Aggregating file.csv (files_copied)")
    from file_agg import run_file_agg
    run_file_agg()

    print_banner("3d", "Aggregating email.csv (emails_sent, external_emails, emails_with_attachments)")
    from email_agg import run_email_agg
    run_email_agg()

    print_banner("3e", "Aggregating http.csv (websites_visited)")
    from http_agg import run_http_agg
    run_http_agg()

    # 4. Pipeline A: Outer Join & LDAP Department Fallback
    print_banner(4, "Outer Joining Daily Tables & Attaching LDAP Metadata")
    from cert_merge_ldap import run_merge_and_ldap
    run_merge_and_ldap()

    # 5. Pipeline A: Time-Scoped Ground Truth Labeling & D-01..D-07 Validation
    print_banner(5, "Applying Time-Scoped Malicious Labels & Validation")
    from cert_label_validate import run_label_and_validate
    run_label_and_validate()

    # 6. Stream Parquet to PostgreSQL & Create Primary Keys / Indexes
    print_banner(6, "Streaming Parquet into PostgreSQL 15 & Creating Indexes")
    from load_to_postgres import stream_parquet_to_postgres, build_indexes_and_verify, CERT_PARQUET, CICIDS_PARQUET
    stream_parquet_to_postgres(CERT_PARQUET, "user_daily_activity", batch_size=100_000)
    stream_parquet_to_postgres(CICIDS_PARQUET, "network_flows_clean", batch_size=100_000)
    build_indexes_and_verify()

    elapsed = time.time() - t_start
    print("\n" + "=" * 75)
    print(f"MODULE 1 PIPELINE COMPLETED SUCCESSFULLY IN {elapsed:.1f}s!")
    print("Both tables are fully populated, indexed, and ready for Module 2.")
    print("=" * 75)

if __name__ == "__main__":
    main()
