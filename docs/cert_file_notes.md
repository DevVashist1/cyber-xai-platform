# CERT Insider Threat Dataset (v4.2) — File Inventory & Notes

This document fulfills the **Step 4.1 deliverable** of Module 1: inspecting and understanding each CERT log file before executing aggregation logic.

---

## 1. Dataset Overview

* **Dataset Source:** Carnegie Mellon University (CMU) CERT Insider Threat Test Dataset, Release `r4.2`.
* **Nature:** Synthetic simulation of enterprise computer and communication activity over an 18-month timeline (January 2010 to June 2011).
* **Population:** 1,000 employees with diverse roles across departments.
* **Malicious Insiders:** 70 specific users involved in planted insider threat scenarios across defined attack time windows (`answers/insiders.csv`).

---

## 2. File-by-File Inventory

### 2.1 `logon.csv`
* **What each row represents:** A single logon or logoff event by an employee on an enterprise workstation.
* **Columns:**
  - `id` (string): Unique identifier for the logon/logoff record.
  - `date` (datetime string `%m/%d/%Y %H:%M:%S`): Timestamp of the event.
  - `user` (string): Employee user identifier (e.g., `AAM0658`).
  - `pc` (string): Workstation identifier (e.g., `PC-1234`).
  - `activity` (string): Type of event (`Logon` or `Logoff`).
* **Processing Decisions:**
  - Filtered exclusively to `activity == 'Logon'`.
  - Normal working hours defined as **07:00 to 19:00 on Monday–Friday**. Logons outside this window or on weekends are counted as `after_hours_logons`.
  - Count distinct `pc` values per user-day as `distinct_pcs` (captures lateral movement or abnormal workstation hopping).

---

### 2.2 `device.csv`
* **What each row represents:** A single connection or disconnection event of a removable USB mass storage device.
* **Columns:**
  - `id` (string): Unique event record ID.
  - `date` (datetime string `%m/%d/%Y %H:%M:%S`): Timestamp of the connect/disconnect event.
  - `user` (string): Employee identifier.
  - `pc` (string): Workstation where the USB was inserted.
  - `activity` (string): `Connect` or `Disconnect`.
* **Processing Decisions:**
  - Filtered strictly to `activity == 'Connect'`.
  - Daily count aggregated as `usb_connects`.
  - Connects occurring outside 07:00–19:00 or on weekends aggregated as `after_hours_usb_connects`.

---

### 2.3 `file.csv`
* **What each row represents:** A single file system access, copy, or write event onto an external or internal drive.
* **Columns:**
  - `id` (string): Unique file transaction ID.
  - `date` (datetime string `%m/%d/%Y %H:%M:%S`): Event timestamp.
  - `user` (string): Employee performing the action.
  - `pc` (string): Machine on which the action occurred.
  - `filename` (string): File path or document name.
  - `content` (string): Extracted text content of the file.
* **Processing Decisions:**
  - Daily volume aggregated as `files_copied` per `(user_id, date)`.
  - Raw `content` and `filename` are skipped during daily aggregation to conserve memory and optimize throughput.

---

### 2.4 `email.csv`
* **What each row represents:** A single outbound or internal email communication event.
* **Columns:**
  - `id` (string): Unique email message ID.
  - `date` (datetime string `%m/%d/%Y %H:%M:%S`): Time email was dispatched.
  - `user` (string): Sender employee ID.
  - `pc` (string): Workstation from which email was sent.
  - `to` (string): Semicolon-delimited list of primary recipient email addresses.
  - `cc` (string): Semicolon-delimited CC recipients.
  - `bcc` (string): Semicolon-delimited BCC recipients.
  - `from` (string): Sender email address (`<user>@dtaa.com`).
  - `size` (integer): Total message size in bytes.
  - `attachments` (integer): Number of attached files.
  - `content` (string): Body text of the email.
* **Processing Decisions:**
  - Daily aggregated `emails_sent`.
  - `external_emails`: Count of emails where at least one recipient does not end in `@dtaa.com`.
  - `emails_with_attachments`: Count of emails where `attachments > 0`.
  - Flags for large emails (`>= 1,000,000` bytes) and total recipients.

---

### 2.5 `http.csv`
* **What each row represents:** A single HTTP web browsing request made by a user.
* **Columns:**
  - `id` (string): Unique web request ID.
  - `date` (datetime string `%m/%d/%Y %H:%M:%S`): Request timestamp.
  - `user` (string): Employee browsing the web.
  - `pc` (string): Workstation identifier.
  - `url` (string): Full target URL.
  - `content` (string): Webpage title/content snippet.
* **Processing Decisions:**
  - Extracted clean domain names using standard URL regex (`^(?:[a-zA-Z]+://)?(?:www\.)?([^/:?#]+)`).
  - Aggregated daily count of distinct sites visited as `websites_visited`.

---

### 2.6 `LDAP/*.csv`
* **What each row represents:** Monthly organizational snapshot (18 files from `2010-01.csv` to `2011-06.csv`) capturing employee employment status, role, and reporting structure.
* **Columns:**
  - `user_id` (string): Employee identifier.
  - `employee_name` (string): Full name.
  - `email` (string): Company email.
  - `role` (string): Job title.
  - `projects` (string): Active project assignments.
  - `department` (string): Organizational department.
  - `functional_unit` (string): Higher-level business group.
  - `supervisor` (string): Direct manager.
* **Processing Decisions:**
  - Deduplicated by `user_id` keeping the latest snapshot.
  - Applied robust fallback: where `department` is null/empty (e.g. executive leadership), fallback to `functional_unit`, then `role`. This guarantees **0 unassigned departments** across all 1,000 employees.

---

### 2.7 `answers/insiders.csv`
* **What each row represents:** Ground truth record for synthetic malicious scenarios injected into the dataset.
* **Columns:**
  - `dataset` (string/float): Dataset version (filtered strictly to `4.2`).
  - `scenario` (integer): Threat scenario number (1, 2, or 3).
  - `details` (string): Narrative description of the malicious activity.
  - `user` (string): Malicious employee identifier.
  - `start` (datetime string): Start date of the malicious activity window.
  - `end` (datetime string): End date of the malicious activity window.
* **Processing Decisions:**
  - Time-scoped labeling: `is_malicious = 1` ONLY for user-day records where `date >= start_date` and `date <= end_date`. All other dates for that user remain `0`.
