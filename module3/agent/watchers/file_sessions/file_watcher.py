import os
import uuid
from pathlib import Path
from datetime import datetime, timezone

IGNORED_DIRS = {"$recycle.bin", "system volume information", ".trashes"}
SENSITIVE_EXTS = {"csv", "xlsx", "xls", "docx", "pdf", "sql", "db", "sqlite", "pem", "key", "env", "kdbx", "pfx"}
ARCHIVE_EXTS = {"zip", "rar", "7z", "tar", "gz"}


class FileCopySessionWatcher:
    def __init__(self, outbox, quiet_seconds: float = 15.0):
        self.outbox = outbox
        self.quiet_seconds = quiet_seconds
        self.sessions = {}

    def start_session(self, volume_hash: str, usb_connect_event_id: str = None, started_at: str = None):
        if volume_hash not in self.sessions:
            self.sessions[volume_hash] = {
                "volume_serial_hash": volume_hash,
                "usb_connect_event_id": usb_connect_event_id,
                "session_start": started_at or datetime.now(timezone.utc).isoformat(),
                "files": {},
                "is_partial": False
            }

    def record_file_event(self, volume_hash: str, file_path: str, initial_size: int = 0, usb_connect_event_id: str = None):
        norm = str(file_path).replace("\\", "/")
        parts = [p.lower() for p in norm.split("/") if p]
        if any(p in IGNORED_DIRS for p in parts):
            return False
        fname = parts[-1] if parts else ""
        if fname.startswith("~$") or fname.endswith(".tmp"):
            return False

        if volume_hash not in self.sessions:
            self.start_session(volume_hash, usb_connect_event_id)

        sess = self.sessions[volume_hash]
        sess["files"][file_path] = initial_size
        if len(sess["files"]) >= 100000:
            sess["is_partial"] = True
            self.close_session(volume_hash)
        return True

    def close_session(self, volume_hash: str, is_partial: bool = False, ended_at: str = None):
        sess = self.sessions.pop(volume_hash, None)
        if not sess or not sess["files"]:
            return None

        total_bytes = 0
        max_bytes = 0
        ext_hist = {}
        sens_count = 0
        arch_count = 0

        for fpath, fallback_sz in sess["files"].items():
            final_sz = fallback_sz
            try:
                if os.path.exists(fpath):
                    final_sz = os.path.getsize(fpath)
            except Exception:
                pass
            total_bytes += final_sz
            if final_sz > max_bytes:
                max_bytes = final_sz

            ext = Path(fpath).suffix.lower().lstrip(".") or "none"
            ext_hist[ext] = ext_hist.get(ext, 0) + 1
            if ext in SENSITIVE_EXTS:
                sens_count += 1
            if ext in ARCHIVE_EXTS:
                arch_count += 1

        end_iso = ended_at or datetime.now(timezone.utc).isoformat()
        ev = {
            "event_id": str(uuid.uuid4()),
            "event_type": "file_transfer",
            "occurred_at": end_iso,
            "session_start": sess["session_start"],
            "session_end": end_iso,
            "volume_serial_hash": volume_hash,
            "usb_connect_event_id": sess["usb_connect_event_id"],
            "file_count": len(sess["files"]),
            "total_bytes": total_bytes,
            "max_file_bytes": max_bytes,
            "ext_histogram": ext_hist,
            "sensitive_ext_count": sens_count,
            "archive_count": arch_count,
            "duration_seconds": 5,
            "is_partial": bool(is_partial or sess["is_partial"]),
            "risk_tier": "high" if (len(sess["files"]) >= 200 or sens_count >= 5) else "medium"
        }
        self.outbox.enqueue(ev)
        return ev

    def flush_on_unplug(self, volume_hash: str):
        return self.close_session(volume_hash, is_partial=True)
