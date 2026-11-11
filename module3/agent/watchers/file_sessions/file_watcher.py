import os
import time
import uuid
import threading
from pathlib import Path
from datetime import datetime, timezone

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    Observer = None
    FileSystemEventHandler = object

IGNORED_DIRS = {"$recycle.bin", "system volume information", ".trashes"}
SENSITIVE_EXTS = {"csv", "xlsx", "xls", "docx", "pdf", "sql", "db", "sqlite", "pem", "key", "env", "kdbx", "pfx"}
ARCHIVE_EXTS = {"zip", "rar", "7z", "tar", "gz"}


class _UsbDriveEventHandler(FileSystemEventHandler):
    def __init__(self, watcher, volume_hash: str, connect_eid: str):
        super().__init__()
        self.watcher = watcher
        self.volume_hash = volume_hash
        self.connect_eid = connect_eid

    def on_created(self, event):
        if not getattr(event, "is_directory", False):
            self.watcher.record_file_event(self.volume_hash, event.src_path, usb_connect_event_id=self.connect_eid)

    def on_moved(self, event):
        if not getattr(event, "is_directory", False):
            self.watcher.record_file_event(self.volume_hash, event.dest_path, usb_connect_event_id=self.connect_eid)


class FileCopySessionWatcher:
    def __init__(self, outbox, quiet_seconds: float = 15.0, max_session_seconds: float = 1800.0):
        self.outbox = outbox
        self.quiet_seconds = quiet_seconds
        self.max_session_seconds = max_session_seconds
        self.sessions = {}
        self.observers = {}
        self._lock = threading.Lock()

    def start_watching_drive(self, drive_letter: str, volume_hash: str, usb_connect_event_id: str = None):
        """Step U5 & F1: Start recursive watchdog observer on mounted USB drive root."""
        if Observer is None or not drive_letter:
            return
        root_path = f"{drive_letter.rstrip('\\/')}\\"
        if not os.path.exists(root_path) or volume_hash in self.observers:
            return
        try:
            handler = _UsbDriveEventHandler(self, volume_hash, usb_connect_event_id)
            obs = Observer()
            obs.schedule(handler, root_path, recursive=True)
            obs.daemon = True
            obs.start()
            self.observers[volume_hash] = obs
        except Exception:
            pass

    def stop_watching_drive(self, volume_hash: str):
        obs = self.observers.pop(volume_hash, None)
        if obs is not None:
            try:
                obs.stop()
                obs.join(timeout=1.0)
            except Exception:
                pass

    def start_session(self, volume_hash: str, usb_connect_event_id: str = None, started_at: str = None):
        now_ts = time.time()
        if volume_hash not in self.sessions:
            self.sessions[volume_hash] = {
                "volume_serial_hash": volume_hash,
                "usb_connect_event_id": usb_connect_event_id,
                "session_start": started_at or datetime.now(timezone.utc).isoformat(),
                "start_ts": now_ts,
                "last_event_ts": now_ts,
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

        with self._lock:
            if volume_hash not in self.sessions:
                self.start_session(volume_hash, usb_connect_event_id)

            sess = self.sessions[volume_hash]
            sess["last_event_ts"] = time.time()
            sess["files"][file_path] = initial_size
            if len(sess["files"]) >= 100000 or (sess["last_event_ts"] - sess["start_ts"]) >= self.max_session_seconds:
                sess["is_partial"] = True
                self.close_session(volume_hash)
        return True

    def check_idle_sessions(self, now_ts: float = None):
        """Step F2: Close open sessions after 15 seconds of quiet (or 30m cap)."""
        now_ts = now_ts or time.time()
        to_close = []
        with self._lock:
            for vhash, sess in list(self.sessions.items()):
                if sess["files"] and (now_ts - sess["last_event_ts"]) >= self.quiet_seconds:
                    to_close.append((vhash, False))
                elif sess["files"] and (now_ts - sess["start_ts"]) >= self.max_session_seconds:
                    to_close.append((vhash, True))
        closed = []
        for vhash, partial in to_close:
            ev = self.close_session(vhash, is_partial=partial)
            if ev:
                closed.append(ev)
        return closed

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
        dur = max(1, int(time.time() - sess.get("start_ts", time.time())))
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
            "duration_seconds": dur,
            "is_partial": bool(is_partial or sess["is_partial"]),
            "risk_tier": "high" if (len(sess["files"]) >= 200 or sens_count >= 5) else "medium"
        }
        self.outbox.enqueue(ev)
        return ev

    def flush_on_unplug(self, volume_hash: str):
        self.stop_watching_drive(volume_hash)
        return self.close_session(volume_hash, is_partial=True)
