# Cybersecurity & XAI Platform — Module 1: Data Ingestion & Preprocessing

This repository contains **Module 1** of our 9-module cybersecurity platform combining Insider Threat Detection, Network Attack Forecasting, and Explainable AI (SHAP). Module 1 ingests two raw public datasets (CERT Insider Threat `r4.2` and `CICIDS2017`), cleans and aggregates them via staging Parquet pipelines, and loads them into two indexed **PostgreSQL 15** tables inside Docker.

---

## 1. Datasets & Exact Sources

1. **CERT Insider Threat Dataset (Version `r4.2`)**
   - **Source:** [CMU Kilthub Insider Threat Dataset](https://kilthub.cmu.edu/articles/dataset/Insider_Threat_Test_Dataset/12841247)
   - **Files Used:** `logon.csv`, `device.csv`, `file.csv`, `email.csv`, `http.csv`, monthly `LDAP/*.csv` snapshots, and `answers/insiders.csv`.
2. **CICIDS2017 Network Traffic Dataset**
   - **Source:** [UNB Canadian Institute for Cybersecurity (IDS 2017)](https://www.unb.ca/cic/datasets/ids-2017.html)
   - **Version Used:** `GeneratedLabelledFlows.zip` (`TrafficLabelling_` — 8 daily CSV files containing flow features, `Timestamp`, `Source IP`, and `Destination IP`).

---

## 2. Three-Zone Folder Architecture Rule (Section 3)

To guarantee reproducibility and prevent downstream data corruption, the repository enforces a strict three-zone boundary:

1. **Raw Data Zone (`data/raw/`):** Strictly **read-only**. Contains the original extracted CERT `r4.2` and `CICIDS2017` CSV files. No script or teammate ever modifies these files.
2. **Intermediate Working Zone (`data/intermediate/`):** **Disposable** staging area containing `.parquet` files generated during cleaning and daily aggregation. Safe to delete and regenerate at any time.
3. **Final Output Zone (PostgreSQL 15 via Docker):** The **only** source of truth (`user_daily_activity` and `network_flows_clean`) that downstream modules (Modules 2 through 9) are permitted to query.

---

## 3. Pipeline Decisions & Cleaning Methodology

### Pipeline A: CERT `r4.2` (`user_daily_activity`)
- **Timestamp Standardization (Step 4.2):** All raw event timestamps (`%m/%d/%Y %H:%M:%S`) are explicitly parsed and normalized to calendar dates prior to grouping.
- **Event Filtering & Daily Aggregation (Step 4.3 & Addendum Section C):**
  - `logon.csv`: Filtered strictly to `activity == 'Logon'`. Normal working hours defined as **07:00 to 19:00 on Monday–Friday**. Logons outside this window or on weekends are counted as `after_hours_logons`. Count of unique machines logged into that day is tracked as `distinct_pcs`.
  - `device.csv`: Filtered strictly to `activity == 'Connect'`. USB connections counted as `usb_connects`, and connects outside working hours counted as `after_hours_usb_connects`.
  - `file.csv`: Aggregated total file events per `(user_id, date)` as `files_copied`.
  - `email.csv`: Aggregated `emails_sent`, `external_emails` (emails to domains other than `@dtaa.com`), `emails_with_attachments`, and large email/byte counts.
  - `http.csv`: Extracted normalized domain names and counted distinct `websites_visited` per `(user_id, date)`.
- **Outer Join & Zero-Filling (Step 4.4):** Combined all 5 daily tables using an **outer join** on `(user_id, date)` so days with partial activity are never dropped. Missing activity counts are filled with `0`.
- **LDAP Department Fallback (Step 4.5):** Joined organizational metadata from the 18 monthly `LDAP` snapshots. Where `department` is `NaN` in LDAP (e.g., executives), the pipeline falls back to `functional_unit` and `role`, resulting in **0 unassigned departments** across all 1,000 users.
- **Time-Scoped Ground-Truth Labeling (Step 4.6):** Using `answers/insiders.csv` (filtered to `dataset == 4.2`, 70 malicious users), `is_malicious = 1` is applied **only** to `(user_id, date)` rows falling within each insider's documented `[start_date, end_date]` attack window (`1,364` malicious user-days). The remaining `14,080` normal workdays of those 70 users are kept as `is_malicious = 0` to prevent poisoning downstream anomaly detection models.
- **Django Surrogate Key (Addendum Section C):** `row_id bigint PRIMARY KEY` added as the first column to satisfy Django unmanaged model constraints. Unique constraint and index enforced on `(user_id, date)` and index on `(date)`.

### Pipeline B: CICIDS2017 (`network_flows_clean`)
- **Source Day Preservation (Step 5.1):** Preserved `source_day` from each of the 8 daily capture filenames to support chronological splitting in Module 4.
- **Defect Removal (Step 5.2 & 5.4):** Stripped leading/trailing whitespace from all ~80 column names, dropped `291,469` blank/`NaN`/`Infinity` artifact rows, and removed `199` duplicate rows.
- **Scope Decision on Ultra-Rare Attack Classes (Step 5.3):** Explicitly excluded 3 ultra-rare classes with insufficient sample counts across the 2.83M row dataset (`Infiltration`: 36 rows, `Web Attack - Sql Injection`: 21 rows, `Heartbleed`: 11 rows — 68 rows total) as a documented limitation. Encoded the remaining 12 well-represented classes (`0` to `11`).
- **Chronological Ordering & PK (Step 5.5 & Addendum C):** Parsed `timestamp` (`2017-07-03 01:00:01` to `2017-07-07 12:59:00`), sorted all `2,827,609` clean flows chronologically, added `row_id bigint PRIMARY KEY` and indexed on `timestamp`.

---

## 4. Documentation & Schema Contracts

All architecture contracts and frozen designs are documented under [`docs/`](file:///c:/Users/gupta/cyber-xai-platform/docs):
- [`docs/contracts/table_schemas.md`](file:///c:/Users/gupta/cyber-xai-platform/docs/contracts/table_schemas.md): Frozen table schemas, column types, and database indexes.
- [`docs/decisions.md`](file:///c:/Users/gupta/cyber-xai-platform/docs/decisions.md): Architecture decisions log (after-hours window, leave rules, rare class scope).
- [`docs/cert_file_notes.md`](file:///c:/Users/gupta/cyber-xai-platform/docs/cert_file_notes.md): Step 4.1 file inventory and column explanations.

---

## 5. Reproducible Execution Order (From Fresh Clone)

Teammates can execute the complete end-to-end pipeline with zero manual intervention using the single master runner:

```powershell
# 1. Start PostgreSQL 15 in Docker & activate virtual environment
docker compose up -d
py -3.11 -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt

# 2. Run the Master Orchestrator (Steps 1 through 7 end-to-end)
python src\run_pipeline.py
```

*(Alternatively, scripts can be run individually in order: `verify_setup.py` -> `step5_clean_cicids.py` -> `logon_agg.py` -> `device_agg.py` -> `file_agg.py` -> `email_agg.py` -> `http_agg.py` -> `cert_merge_ldap.py` -> `cert_label_validate.py` -> `load_to_postgres.py`)*
