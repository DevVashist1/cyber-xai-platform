import os
import sys
import time
import json
import random
import hashlib
import getpass
import platform
import argparse
import threading
from datetime import datetime, timezone
from pathlib import Path
import requests
import psutil

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from module3.agent.core.agent_core import (
    SingleInstanceLock, CredentialStore, SQLiteOutbox,
    LifecycleMarker, WatcherSupervisor, setup_agent_logger
)
from module3.agent.watchers.usb.usb_watcher import UsbWatcher
from module3.agent.watchers.file_sessions.file_watcher import FileCopySessionWatcher
from module3.agent.watchers.clipboard.clipboard_watcher import ClipboardAndAppWatcher
from module3.agent.ui.tray import AgentTrayUI, TRANSPARENCY_NOTE


class EndpointAgentRuntime:
    def __init__(self, api_base: str, user_id: str, enrollment_code: str, runtime_dir: Path):
        self.api_base = api_base.rstrip("/")
        self.user_id = user_id
        self.enrollment_code = enrollment_code
        self.runtime_dir = Path(runtime_dir)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

        self.logger = setup_agent_logger(self.runtime_dir / "logs")
        self.outbox = SQLiteOutbox(self.runtime_dir / "outbox.sqlite3", max_events=50000)
        self.marker = LifecycleMarker(self.runtime_dir / "running.lock")
        self.supervisor = WatcherSupervisor(self.logger)
        self.stop_event = threading.Event()
        self.started_at_iso = datetime.now(timezone.utc).isoformat()
        self.config_version = 1
        self.config_cache_path = self.runtime_dir / "config_cache.json"

        self.file_watcher = FileCopySessionWatcher(self.outbox)
        self.usb_watcher = UsbWatcher(self.outbox, file_session_watcher=self.file_watcher)
        self.cb_watcher = ClipboardAndAppWatcher(self.outbox)

        self.device_id = None
        self.device_token = None

    def ensure_registered(self) -> bool:
        did, tok = CredentialStore.load_credentials(self.user_id)
        token_file = self.runtime_dir / f".cred_{self.user_id}.json"
        if (not did or not tok) and token_file.exists():
            try:
                saved = json.loads(token_file.read_text(encoding="utf-8"))
                did, tok = saved.get("device_id"), saved.get("device_token")
            except Exception:
                pass

        if did and tok:
            self.device_id, self.device_token = did, tok
            return True

        os_user_hash = hashlib.sha256(getpass.getuser().encode("utf-8")).hexdigest()
        hostname_hash = hashlib.sha256(platform.node().encode("utf-8")).hexdigest()
        payload = {
            "enrollment_code": self.enrollment_code,
            "user_id": self.user_id,
            "device_kind": "agent",
            "client_version": "1.0.0",
            "os_user_hash": os_user_hash,
            "hostname_hash": hostname_hash,
            "os_version": f"{platform.system()} {platform.release()}"
        }
        res = requests.post(f"{self.api_base}/devices/register", json=payload, timeout=5)
        res.raise_for_status()
        data = res.json()
        self.device_id = data["device_id"]
        self.device_token = data["device_token"]
        CredentialStore.save_credentials(self.user_id, self.device_id, self.device_token)
        token_file.write_text(json.dumps({"device_id": self.device_id, "device_token": self.device_token}), encoding="utf-8")
        return True

    def sync_config(self):
        headers = {"Authorization": f"Bearer {self.device_token}"}
        try:
            r = requests.get(f"{self.api_base}/config/agent?current={self.config_version}", headers=headers, timeout=5)
            if r.status_code == 200:
                body = r.json()
                if body.get("status") != "not_modified" and "content" in body:
                    self.config_version = int(body.get("version", self.config_version))
                    self.config_cache_path.write_text(json.dumps(body["content"], indent=2), encoding="utf-8")
        except Exception:
            pass

    def flush_outbox_once(self) -> int:
        batch = self.outbox.fetch_batch(limit=100)
        if not batch:
            return 0
        eids = [item[0] for item in batch]
        events = [item[1] for item in batch]
        headers = {"Authorization": f"Bearer {self.device_token}"}
        r = requests.post(f"{self.api_base}/agent/events", json={"events": events}, headers=headers, timeout=5)
        if r.status_code in (200, 201, 202):
            self.outbox.ack_batch(eids)
            return len(eids)
        return 0

    def send_heartbeat_once(self) -> bool:
        proc = psutil.Process(os.getpid())
        hb_payload = {
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "agent_started_at": self.started_at_iso,
            "client_version": "1.0.0",
            "queue_depth": self.outbox.depth(),
            "dropped_events_total": self.outbox.dropped_events_total,
            "watcher_status": self.supervisor.status,
            "events_sent_since_last": self.outbox.events_sent_since_last,
            "low_risk_clipboard_count": self.cb_watcher.low_risk_clipboard_count,
            "cpu_pct": round(proc.cpu_percent(interval=0.05), 2),
            "mem_mb": round(proc.memory_info().rss / (1024 * 1024), 2),
            "config_version": self.config_version
        }
        headers = {"Authorization": f"Bearer {self.device_token}"}
        r = requests.post(f"{self.api_base}/agent/heartbeat", json=hb_payload, headers=headers, timeout=5)
        if r.status_code == 200:
            self.outbox.events_sent_since_last = 0
            self.cb_watcher.low_risk_clipboard_count = 0
            return True
        return False


def main():
    parser = argparse.ArgumentParser(description="Cyber XAI Module 3 OS-Level Endpoint Agent")
    parser.add_argument("--api-base", default=os.environ.get("AGENT_API_BASE_URL", "http://127.0.0.1:8000/api/v1"))
    parser.add_argument("--user-id", default=os.environ.get("AGENT_USER_ID", "EMP001"))
    parser.add_argument("--enrollment-code", default=os.environ.get("AGENT_ENROLLMENT_CODE", "CYBER-XAI-2026"))
    parser.add_argument("--runtime-dir", default="module3/runtime")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    lock = SingleInstanceLock()
    if not lock.acquire():
        print("[!] Another instance of Cyber XAI Endpoint Agent is already running. Exiting quietly (G1).")
        sys.exit(0)

    try:
        print(f"[*] {TRANSPARENCY_NOTE}\n")
        agent = EndpointAgentRuntime(args.api_base, args.user_id, args.enrollment_code, Path(args.runtime_dir))
        agent.ensure_registered()
        agent.marker.check_unclean_restart_and_mark_running(agent.outbox)
        agent.sync_config()
        agent.send_heartbeat_once()
        sent = agent.flush_outbox_once()
        print(f"[+] Connected to backend as device_id={agent.device_id} (user={agent.user_id}) | Heartbeat OK | Flushed {sent} queued events.")

        if args.once:
            agent.marker.mark_graceful_stop(agent.outbox, reason="checkpoint_once_exit")
            agent.flush_outbox_once()
            print("[+] Setup checkpoint (--once) completed cleanly.")
            return
    finally:
        lock.release()


if __name__ == "__main__":
    main()
