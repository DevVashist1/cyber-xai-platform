# Platform Architectural Decisions Log

This document records the foundational design decisions, thresholds, and data definitions for Module 1 and Module 2, fulfilling Section B and Section F of the Module 1 Addendum.

---

## Decision D-01: Two-Tier Logon Window Architecture (Global vs Personal)
* **Date:** 2026-10-25
* **Context:** A single static threshold cannot detect subtle shift anomalies (e.g., an employee whose fixed shift is 10:00–18:00 logging in at 07:15). A two-tier approach is established:
* **Resolution:**
  1. **Global Window (07:00 – 19:00 Weekdays, Module 1):**
     - Overall enterprise office operating hours covering ~96.4% of all normal logons.
     - Any activity before 07:00, after 19:00 (`hour >= 19`), or on weekends (`weekday >= 5`) is aggregated as `after_hours_logons` and `after_hours_usb_connects` in `user_daily_activity`.
  2. **Personal Local Window (User-Specific Baseline, Module 2):**
     - Because each employee has fixed shift habits (e.g. User A regularly works 07:00–15:00 while User B works 09:30–18:00), Module 2 builds a personalized baseline from each user's **first 30 active days** (Frozen Baseline).
     - If an employee logs in outside their personal shift pattern—even if technically within the 07:00–19:00 Global Window—the Module 2 XGBoost baseline and z-score anomaly detectors flag this localized deviation immediately.

---

## Decision D-02: CERT Dataset Release Version Pinning
* **Date:** 2026-10-25
* **Context:** Multiple releases of the CMU CERT dataset exist (`r4.1`, `r4.2`, `r5.2`, `r6.2`), each with varying column schemas, user counts, and planted insider scenarios. Mixing releases introduces silent corruption.
* **Resolution:**
  - Standardize strictly on **CERT Release `r4.2`**.
  - In `answers/insiders.csv`, rows are filtered explicitly to `dataset == '4.2'`, identifying 70 documented malicious insider users spanning 1,364 malicious user-day records.

---

## Decision D-03: Time-Scoped Ground Truth Labeling Strategy
* **Date:** 2026-10-25
* **Context:** Malicious insiders in CERT act maliciously only during specific time windows (e.g., 2 weeks prior to departure). Marking an entire employment history as malicious trains ML models to associate normal everyday behavior with attacks.
* **Resolution:**
  - For each insider in `answers/insiders.csv`, mark `is_malicious = 1` ONLY for days falling within `[start_date, end_date]`.
  - All days prior to and following the attack window are marked `is_malicious = 0`.
  - Out of 15,444 total workdays for the 70 insiders, 1,364 are labeled `1` and 14,080 are preserved as `0`.

---

## Decision D-04: CICIDS2017 Rare Attack Class Exclusion Scope
* **Date:** 2026-10-25
* **Context:** In CICIDS2017 (~2.83M records), several simulated attack types have extremely few samples (e.g., Heartbleed has 11 samples, SQL Injection has 21 samples, Infiltration has 36 samples). Such classes cannot be reliably split into train/val/test or learned by classifiers.
* **Resolution:**
  - Exclude the 3 ultra-rare classes (`Heartbleed`, `Web Attack - Sql Injection`, `Infiltration` — 68 rows total) from the core benchmark.
  - Retain and encode the 12 well-represented attack classes (`BENIGN`, `DoS Hulk`, `PortScan`, `DDoS`, `DoS GoldenEye`, `FTP-Patator`, `SSH-Patator`, `DoS slowloris`, `DoS Slowhttptest`, `Bot`, `Web Attack - Brute Force`, `Web Attack - XSS`).
  - Document this explicit limitation in research viva reports.

---

## Decision D-05: Surrogate Primary Key (`row_id`) Addition for Django ORM
* **Date:** 2026-10-25
* **Context:** Module 2 implements a Django REST Framework backend where Module 1's tables (`user_daily_activity` and `network_flows_clean`) are consumed as unmanaged models (`managed = False`). Standard Django models require a single-column primary key and do not natively support composite keys like `(user_id, date)`.
* **Resolution:**
  - Added `row_id bigint PRIMARY KEY` as the first column to both `user_daily_activity` and `network_flows_clean`.
  - Enforced a database-level `UNIQUE (user_id, date)` constraint and composite index on `user_daily_activity`.

---

## Decision D-06: Inferred Leave Rule Definition (Module 2 Baseline)
* **Date:** 2026-10-25
* **Context:** CERT does not provide official HR leave records. However, planted scenarios feature employees returning after an absence to exfiltrate data.
* **Resolution:**
  - An employee is inferred to be on leave when they have had no logged activity for **5 or more consecutive working days**.
  - Any first activity following this absence that occurs after-hours or on a weekend raises an automated medium-severity rule flag.
