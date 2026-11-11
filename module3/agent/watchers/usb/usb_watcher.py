import time
import uuid
import hashlib
from datetime import datetime, timezone

DEPLOYMENT_SALT = "cyber_xai_usb_salt_2026"

def hash_volume_serial(raw_serial: str) -> str:
    return hashlib.sha256(f"{DEPLOYMENT_SALT}:{raw_serial}".encode("utf-8")).hexdigest()


class UsbWatcher:
    def __init__(self, outbox, file_session_watcher=None, debounce_seconds: float = 3.0):
        self.outbox = outbox
        self.file_session_watcher = file_session_watcher
        self.debounce_seconds = debounce_seconds
        self.last_connect_time = {}
        self.active_volumes = {}

    @staticmethod
    def classify_device(drive_type: int, interface_type: str = "", pnp_device_id: str = "") -> str:
        pnp_up = (pnp_device_id or "").upper()
        iface_up = (interface_type or "").upper()
        if "HID\\" in pnp_up or "KEYBOARD" in pnp_up or "MOUSE" in pnp_up:
            return "ignored_hid"
        if "MTP" in pnp_up or "WPD" in pnp_up or "PORTABLE" in iface_up:
            return "mtp"
        if drive_type == 2 or (drive_type == 3 and ("USB" in iface_up or "USBSTOR" in pnp_up)):
            return "mass_storage"
        return "ignored"

    def handle_arrival(self, raw_serial: str, drive_letter: str = "E:", drive_type: int = 2,
                       interface_type: str = "USB", pnp_id: str = "USBSTOR\\DISK",
                       vid_pid: str = "0781:5567", capacity_gb: float = 32.0, fs_type: str = "FAT32",
                       now_ts: float = None, occurred_at: str = None):
        dev_class = self.classify_device(drive_type, interface_type, pnp_id)
        if dev_class.startswith("ignored"):
            return None

        vol_hash = hash_volume_serial(raw_serial) if raw_serial else None
        now_ts = now_ts if now_ts is not None else time.time()

        if vol_hash and vol_hash in self.last_connect_time:
            if (now_ts - self.last_connect_time[vol_hash]) < self.debounce_seconds:
                return None
        if vol_hash:
            self.last_connect_time[vol_hash] = now_ts

        eid = str(uuid.uuid4())
        ev = {
            "event_id": eid,
            "event_type": "usb_connect",
            "occurred_at": occurred_at or datetime.now(timezone.utc).isoformat(),
            "device_class": dev_class,
            "drive_letter": drive_letter if dev_class == "mass_storage" else None,
            "volume_serial_hash": vol_hash,
            "usb_vid_pid": vid_pid,
            "capacity_gb": capacity_gb if dev_class == "mass_storage" else None,
            "fs_type": fs_type if dev_class == "mass_storage" else None,
            "is_encrypted": False,
            "risk_tier": "medium"
        }
        self.outbox.enqueue(ev)
        if vol_hash and dev_class == "mass_storage":
            self.active_volumes[vol_hash] = {"drive_letter": drive_letter, "connect_event_id": eid}
            if self.file_session_watcher and drive_letter:
                self.file_session_watcher.start_session(vol_hash, eid)
        return ev

    def handle_removal(self, raw_serial: str, occurred_at: str = None):
        vol_hash = hash_volume_serial(raw_serial)
        if self.file_session_watcher:
            self.file_session_watcher.flush_on_unplug(vol_hash)
        info = self.active_volumes.pop(vol_hash, {})
        ev = {
            "event_id": str(uuid.uuid4()),
            "event_type": "usb_disconnect",
            "occurred_at": occurred_at or datetime.now(timezone.utc).isoformat(),
            "device_class": "mass_storage",
            "drive_letter": info.get("drive_letter"),
            "volume_serial_hash": vol_hash,
            "risk_tier": "low"
        }
        self.outbox.enqueue(ev)
        return ev
