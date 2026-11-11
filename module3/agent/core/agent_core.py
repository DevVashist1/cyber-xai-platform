import os
import sys
import json
import time
import uuid
import sqlite3
import logging
import threading
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
from pathlib import Path

try:
    import keyring
except ImportError:
    keyring = None

try:
    import win32event
    import win32api
    import winerror
except ImportError:
    win32event = None

KEYRING_SERVICE = "CyberXAI_Module3_Agent"
FORBIDDEN_LOG_PATTERNS = ["BEGIN RSA PRIVATE KEY", "AKIAIOSFODNN7EXAMPLE", "TEST-BLOCK-ME", "SECRET_PLANTED_STRING"]


class PrivacyFilter(logging.Filter):
    def filter(self, record):
        msg = str(record.getMessage())
        for pat in FORBIDDEN_LOG_PATTERNS:
            if pat in msg:
                record.msg = "[REDACTED_BY_PRIVACY_FILTER]"
                record.args = ()
        return True


def setup_agent_logger(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("cyber_xai_agent")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fh = RotatingFileHandler(log_dir / "agent.log", maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        fh.addFilter(PrivacyFilter())
        logger.addHandler(fh)
    return logger


class SingleInstanceLock:
    def __init__(self, mutex_name="Global\\CyberXAI_Endpoint_Agent_Mutex_v1"):
        self.mutex_name = mutex_name
        self.handle = None
        self.already_running = False

    def acquire(self) -> bool:
        if win32event is not None:
            self.handle = win32event.CreateMutex(None, False, self.mutex_name)
            last_err = win32api.GetLastError()
            if last_err == winerror.ERROR_ALREADY_EXISTS:
                self.already_running = True
                return False
            return True
        return True

    def release(self):
        if self.handle and win32api is not None:
            try:
                win32api.CloseHandle(self.handle)
            except Exception:
                pass
            self.handle = None


class CredentialStore:
    @staticmethod
    def save_credentials(user_id: str, device_id: str, token: str):
        if keyring is not None:
            try:
                keyring.set_password(KEYRING_SERVICE, f"{user_id}_device_id", device_id)
                keyring.set_password(KEYRING_SERVICE, f"{user_id}_token", token)
            except Exception:
                pass

    @staticmethod
    def load_credentials(user_id: str):
        if keyring is not None:
            try:
                did = keyring.get_password(KEYRING_SERVICE, f"{user_id}_device_id")
                tok = keyring.get_password(KEYRING_SERVICE, f"{user_id}_token")
                return did, tok
            except Exception:
                pass
        return None, None


class SQLiteOutbox:
    def __init__(self, db_path: Path, max_events: int = 50000):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_events = max_events
        self.dropped_events_total = 0
        self.events_sent_since_last = 0
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS outbox (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    severity_rank INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
            """)
            conn.commit()

    @staticmethod
    def _severity_to_rank(sev: str) -> int:
        return {"low": 1, "medium": 2, "high": 3}.get(str(sev).lower(), 1)

    def enqueue(self, event_dict: dict) -> bool:
        forbidden = {"raw_text", "clipboard_text", "file_name", "filenames", "window_title"}
        if forbidden.intersection(event_dict.keys()):
            raise ValueError("Privacy guard blocked forbidden content field from entering SQLite outbox!")

        eid = event_dict.get("event_id") or str(uuid.uuid4())
        event_dict["event_id"] = eid
        if "occurred_at" not in event_dict:
            event_dict["occurred_at"] = datetime.now(timezone.utc).isoformat()

        sev_rank = self._severity_to_rank(event_dict.get("risk_tier", "medium"))
        with self._lock, sqlite3.connect(self.db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
            if count >= self.max_events:
                victim = conn.execute(
                    "SELECT event_id FROM outbox ORDER BY severity_rank ASC, created_at ASC LIMIT 1"
                ).fetchone()
                if victim:
                    conn.execute("DELETE FROM outbox WHERE event_id = ?", (victim[0],))
                    self.dropped_events_total += 1

            conn.execute(
                "INSERT OR IGNORE INTO outbox (event_id, event_type, severity_rank, created_at, payload_json) VALUES (?, ?, ?, ?, ?)",
                (eid, event_dict["event_type"], sev_rank, event_dict["occurred_at"], json.dumps(event_dict))
            )
            conn.commit()
        return True

    def fetch_batch(self, limit: int = 100) -> list:
        with self._lock, sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT event_id, payload_json FROM outbox ORDER BY created_at ASC LIMIT ?", (limit,)
            ).fetchall()
        return [(r[0], json.loads(r[1])) for r in rows]

    def ack_batch(self, event_ids: list):
        if not event_ids:
            return
        with self._lock, sqlite3.connect(self.db_path) as conn:
            placeholders = ",".join("?" for _ in event_ids)
            conn.execute(f"DELETE FROM outbox WHERE event_id IN ({placeholders})", event_ids)
            conn.commit()
            self.events_sent_since_last += len(event_ids)

    def depth(self) -> int:
        with self._lock, sqlite3.connect(self.db_path) as conn:
            return conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]


class LifecycleMarker:
    def __init__(self, marker_path: Path):
        self.marker_path = Path(marker_path)
        self.marker_path.parent.mkdir(parents=True, exist_ok=True)

    def check_unclean_restart_and_mark_running(self, outbox: SQLiteOutbox) -> bool:
        unclean = self.marker_path.exists()
        if unclean:
            outbox.enqueue({
                "event_id": str(uuid.uuid4()),
                "event_type": "agent_unclean_restart",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "risk_tier": "high"
            })
        self.marker_path.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
        return unclean

    def mark_graceful_stop(self, outbox: SQLiteOutbox, reason: str = "normal_shutdown"):
        outbox.enqueue({
            "event_id": str(uuid.uuid4()),
            "event_type": "agent_stop",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
            "risk_tier": "low"
        })
        if self.marker_path.exists():
            try:
                self.marker_path.unlink()
            except Exception:
                pass


class WatcherSupervisor:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.status = {"usb": "ok", "file": "ok", "clipboard": "ok", "apps": "ok"}
        self.restarts = {k: 0 for k in self.status}

    def run_supervised(self, name: str, target_fn, stop_event: threading.Event):
        def _loop():
            while not stop_event.is_set():
                try:
                    self.status[name] = "ok"
                    target_fn(stop_event)
                    if stop_event.is_set():
                        break
                except Exception as ex:
                    self.restarts[name] += 1
                    self.status[name] = f"error:{type(ex).__name__}"
                    self.logger.error(f"Watcher '{name}' crashed (restart #{self.restarts[name]}): {type(ex).__name__}")
                    time.sleep(0.2)
                    self.status[name] = "ok"
        t = threading.Thread(target=_loop, name=f"watcher_{name}", daemon=True)
        t.start()
        return t
