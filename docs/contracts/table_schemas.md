# Database Schema Contracts (Module 1 & Module 2 Interoperability)

This document freezes the database table definitions in PostgreSQL 15, fulfilling **Section C** of the Module 1 Addendum. Downstream modules (Modules 2 through 9) build against these contracts.

---

## 1. Table: `user_daily_activity`

Aggregated daily behavior for each enterprise employee, joined with organizational LDAP data and time-scoped ground truth labels. Consumed by Module 2 as an unmanaged Django model.

### 1.1 Column Specifications

| Column Name | PostgreSQL Data Type | Nullable | Default | Description / Module 2 Usage |
|---|---|---|---|---|
| `row_id` | `BIGINT` | No | Identity PK | **Primary Key** (surrogate key required by Django ORM) |
| `user_id` | `VARCHAR(32)` | No | — | Employee identifier (e.g., `AAM0658`) |
| `date` | `DATE` | No | — | Calendar date of activity |
| `department` | `VARCHAR(100)` | No | — | Organizational department from LDAP (fallback to unit/role) |
| `logon_count` | `INTEGER` | No | `0` | Total logon events that day |
| `after_hours_logons` | `INTEGER` | No | `0` | Logons outside 07:00–19:00 or on weekends |
| `distinct_pcs` | `INTEGER` | No | `0` | Distinct workstation machines logged into that day |
| `usb_connects` | `INTEGER` | No | `0` | Removable USB connect events that day |
| `after_hours_usb_connects` | `INTEGER` | No | `0` | USB connect events outside 07:00–19:00 or on weekends |
| `files_copied` | `INTEGER` | No | `0` | Total file copy/access operations |
| `emails_sent` | `INTEGER` | No | `0` | Total emails dispatched |
| `external_emails` | `INTEGER` | No | `0` | Outbound emails sent to non-company domains |
| `emails_with_attachments` | `INTEGER` | No | `0` | Emails containing 1 or more attached files |
| `websites_visited` | `INTEGER` | No | `0` | Distinct web domains visited via HTTP |
| `is_malicious` | `SMALLINT` | No | `0` | Ground truth label (`1` inside attack window, `0` otherwise) |

### 1.2 Constraints & Indexes
* **Primary Key:** `PRIMARY KEY (row_id)`
* **Unique Constraint:** `CONSTRAINT uq_user_daily_user_date UNIQUE (user_id, date)`
* **Composite Index:** `CREATE INDEX idx_user_daily_user_date ON user_daily_activity (user_id, date);`
* **Date Index (Peer Group Aggregation):** `CREATE INDEX idx_user_daily_date ON user_daily_activity (date);`
* **Non-Negative Value Integrity:** All integer metric columns must be `>= 0`.

---

## 2. Table: `network_flows_clean`

Cleaned, deduplicated, and chronologically ordered network flow telemetry from the 8-day CICIDS2017 dataset.

### 2.1 Column Specifications

| Column Name | PostgreSQL Data Type | Description |
|---|---|---|
| `row_id` | `BIGINT` | **Primary Key** (surrogate key required by Django ORM) |
| `flow_id` | `INTEGER` | Original sequence flow identifier |
| `timestamp` | `TIMESTAMP` | Normalized datetime of flow capture (`2017-07-03` to `2017-07-07`) |
| `src_ip` | `VARCHAR(45)` | Source IP address |
| `dst_ip` | `VARCHAR(45)` | Destination IP address |
| `duration` | `REAL` / `NUMERIC` | Flow duration in microseconds |
| `packet_count` | `REAL` / `INTEGER` | Total forward packets |
| `byte_count` | `REAL` / `BIGINT` | Total forward length in bytes |
| *[Flow Features]* | `REAL` | ~70 standardized numerical flow statistics |
| `attack_label` | `VARCHAR(64)` | Text attack classification (e.g., `BENIGN`, `DDoS`, `PortScan`) |
| `attack_label_encoded` | `SMALLINT` | Numeric categorical encoding (0 to 11) |
| `source_day` | `VARCHAR(64)` | Name of source capture day/file (preserves temporal boundary) |

### 2.2 Constraints & Indexes
* **Primary Key:** `PRIMARY KEY (row_id)`
* **Timestamp Index:** `CREATE INDEX idx_network_flows_timestamp ON network_flows_clean (timestamp);`
* **Data Quality Guarantees:** 0 rows containing `NaN`, `Infinity`, or duplicate entries.
