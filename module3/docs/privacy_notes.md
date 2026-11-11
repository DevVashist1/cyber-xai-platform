# Module 3 Privacy Design & Data Minimization Notes
1. **Zero Raw Content**: No clipboard text, file names, file contents, or window titles ever leave the host or enter the local SQLite outbox (`X-01`, `X-02`).
2. **Salted Volume Hashing**: USB serials are hashed (`SHA-256`) with a deployment salt before storage.
3. **Password Manager Exclusion**: Clipboard formats `ExcludeClipboardContentFromMonitorProcessing`, `CanIncludeInClipboardHistory`, and `ClipboardViewerIgnore` are skipped immediately (`C-06`).
