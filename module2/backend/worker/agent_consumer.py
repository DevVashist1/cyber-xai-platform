import os
import sys
import json
import time
from datetime import timedelta, timezone as dt_tz
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

import redis
from django.conf import settings
from django.db import transaction
from django.db.models import Sum, Count
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.devices.models import ExtDevice
from apps.behavior.models import BehRuleFlag
from apps.agent_ingest.models import (
    AgtUsbEvent, AgtFileTransferEvent, AgtClipboardEvent,
    AgtAppSession, AgtHeartbeat, AgtHealthAlert, AgtDailyAgg
)

STREAM_NAME = "agent_events"
DLQ_STREAM_NAME = "agent_events_dlq"
GROUP_NAME = "agent_workers"


def parse_dt(val):
    dt = parse_datetime(str(val)) if val else timezone.now()
    if dt and timezone.is_naive(dt):
        dt = timezone.make_aware(dt, dt_tz.utc)
    return dt or timezone.now()


def is_after_hours_time(dt):
    # Shared after-hours window: before 08:00 or >= 19:00, or weekend
    if dt.weekday() >= 5:
        return True
    return dt.hour < 8 or dt.hour >= 19


def raise_agent_flag(user_id, date_val, rule_id, severity, mitre_tag, reason_text):
    BehRuleFlag.objects.create(
        user_id=user_id,
        date=date_val,
        rule_id=rule_id,
        severity=severity,
        source_module="agent",
        mitre_technique=mitre_tag,
        reason=f"[{mitre_tag}] {reason_text}" if mitre_tag else reason_text
    )


def update_daily_agg(user_id, date_val):
    usb_qs = AgtUsbEvent.objects.filter(user_id=user_id, occurred_at__date=date_val, event_type="connect")
    ft_qs = AgtFileTransferEvent.objects.filter(user_id=user_id, session_start__date=date_val)
    cb_qs = AgtClipboardEvent.objects.filter(user_id=user_id, occurred_at__date=date_val)
    app_qs = AgtAppSession.objects.filter(user_id=user_id, started_at__date=date_val)
    gap_qs = AgtHealthAlert.objects.filter(user_id=user_id, started_at__date=date_val, alert_type="heartbeat_gap")
    hb_count = AgtHeartbeat.objects.filter(device__user_id=user_id, received_at__date=date_val).count()

    AgtDailyAgg.objects.update_or_create(
        user_id=user_id,
        date=date_val,
        defaults={
            "usb_connects": usb_qs.count(),
            "after_hours_usb_connects": usb_qs.filter(is_after_hours=True).count(),
            "distinct_usb_devices": usb_qs.exclude(volume_serial_hash__isnull=True).values("volume_serial_hash").distinct().count(),
            "files_copied_to_usb": ft_qs.aggregate(s=Sum("file_count"))["s"] or 0,
            "bytes_copied_to_usb": ft_qs.aggregate(s=Sum("total_bytes"))["s"] or 0,
            "sensitive_ext_files_to_usb": ft_qs.aggregate(s=Sum("sensitive_ext_count"))["s"] or 0,
            "clipboard_medium_count": cb_qs.filter(risk_tier="medium").count(),
            "clipboard_high_count": cb_qs.filter(risk_tier="high").count(),
            "ai_context_clipboard_count": cb_qs.filter(ai_context=True).count(),
            "ai_app_focus_minutes": int((app_qs.aggregate(s=Sum("focus_seconds"))["s"] or 0) // 60),
            "agent_online_minutes": hb_count,
            "agent_gap_count": gap_qs.count(),
        }
    )


def process_single_agent_event(payload: dict) -> str:
    required = ["event_id", "device_id", "user_id", "event_type", "occurred_at"]
    for k in required:
        if k not in payload:
            raise ValueError(f"Missing required field: {k}")

    eid = payload["event_id"]
    etype = payload["event_type"]
    uid = payload["user_id"]
    occ_dt = parse_dt(payload["occurred_at"])
    ev_date = occ_dt.date()
    after_hrs = is_after_hours_time(occ_dt)

    device = ExtDevice.objects.filter(device_id=payload["device_id"]).first()
    if not device:
        raise ValueError(f"Unknown device_id: {payload['device_id']}")

    with transaction.atomic():
        if etype in ("usb_connect", "usb_disconnect"):
            if AgtUsbEvent.objects.filter(event_id=eid).exists():
                return "duplicate_ignored"

            sub_type = "connect" if etype == "usb_connect" else "disconnect"
            vol_hash = payload.get("volume_serial_hash")
            first_seen = False
            if sub_type == "connect" and vol_hash:
                first_seen = not AgtUsbEvent.objects.filter(user_id=uid, volume_serial_hash=vol_hash, event_type="connect").exists()

            AgtUsbEvent.objects.create(
                event_id=eid, device=device, user_id=uid, occurred_at=occ_dt,
                event_type=sub_type, device_class=payload.get("device_class", "mass_storage"),
                drive_letter=payload.get("drive_letter"), volume_serial_hash=vol_hash,
                usb_vid_pid=payload.get("usb_vid_pid"), capacity_gb=payload.get("capacity_gb"),
                fs_type=payload.get("fs_type"), is_encrypted=payload.get("is_encrypted"),
                is_first_seen_for_user=first_seen, is_after_hours=after_hrs
            )

            if sub_type == "connect":
                # Rule AG-01: USB connect outside shared after-hours window
                if after_hrs:
                    raise_agent_flag(uid, ev_date, "AG-01", "low", "T1052.001", "USB storage device connected outside working hours.")
                # Rule AG-02: First-ever use of this USB device by this user
                if first_seen:
                    raise_agent_flag(uid, ev_date, "AG-02", "low", "T1052.001", f"First-ever use of USB volume {str(vol_hash)[:12]} by user {uid}.")

        elif etype == "file_transfer":
            if AgtFileTransferEvent.objects.filter(event_id=eid).exists():
                return "duplicate_ignored"

            s_start = parse_dt(payload.get("session_start") or payload["occurred_at"])
            s_end = parse_dt(payload.get("session_end") or payload["occurred_at"])
            f_count = int(payload.get("file_count", 0))
            t_bytes = int(payload.get("total_bytes", 0))
            sens_count = int(payload.get("sensitive_ext_count", 0))
            arch_count = int(payload.get("archive_count", 0))
            vol_hash = payload.get("volume_serial_hash", "unknown_hash")
            ft_after = is_after_hours_time(s_start)

            # Compute user's historical 95th percentile before inserting
            hist_counts = list(AgtFileTransferEvent.objects.filter(user_id=uid).values_list("file_count", flat=True))
            p95_files = float(sorted(hist_counts)[int(len(hist_counts) * 0.95)]) if len(hist_counts) >= 3 else 50.0

            AgtFileTransferEvent.objects.create(
                event_id=eid, device=device, user_id=uid, session_start=s_start, session_end=s_end,
                volume_serial_hash=vol_hash, usb_connect_event_id=payload.get("usb_connect_event_id"),
                file_count=f_count, total_bytes=t_bytes, max_file_bytes=int(payload.get("max_file_bytes", 0)),
                ext_histogram=payload.get("ext_histogram", {}), sensitive_ext_count=sens_count,
                archive_count=arch_count, duration_seconds=int(payload.get("duration_seconds", 0)),
                is_after_hours=ft_after, is_partial=bool(payload.get("is_partial", False))
            )

            # Rule AG-03: Copy session >= (200 files or 500MB) AND above multiple (1.5x) of user's 95th percentile
            is_large = (f_count >= 200 or t_bytes >= 500 * 1024 * 1024)
            if is_large and f_count >= 1.5 * p95_files:
                raise_agent_flag(uid, ev_date, "AG-03", "high", "T1052.001",
                                 f"Large USB copy session ({f_count} files, {t_bytes} bytes) exceeding user 95th percentile.")

            # Rule AG-04: Sensitive-extension files above count threshold (>= 5) in one session
            if sens_count >= 5:
                raise_agent_flag(uid, ev_date, "AG-04", "medium", "T1052.001",
                                 f"Copied {sens_count} sensitive-extension files onto removable storage in a single session.")

            # Rule AG-05: Archive files created on the drive during a session
            if arch_count >= 1:
                raise_agent_flag(uid, ev_date, "AG-05", "medium", "T1560",
                                 f"Created or copied {arch_count} archive file(s) onto removable drive.")

            # Rule AG-08: After-hours USB connect followed by a large copy session within 10 minutes
            recent_ah_usb = AgtUsbEvent.objects.filter(
                user_id=uid, event_type="connect", is_after_hours=True,
                occurred_at__gte=s_start - timedelta(minutes=10), occurred_at__lte=s_end
            ).exists()
            if (recent_ah_usb or ft_after) and is_large:
                raise_agent_flag(uid, ev_date, "AG-08", "high", "T1052.001",
                                 "After-hours USB connection followed by a large file-copy session within 10 minutes.")

        elif etype == "clipboard":
            if AgtClipboardEvent.objects.filter(event_id=eid).exists():
                return "duplicate_ignored"

            tier = payload.get("risk_tier", "low")
            ai_ctx = bool(payload.get("ai_context", False))
            # Storage policy (Section 5.2): only medium/high or ai_context=True stored individually
            if tier in ("medium", "high") or ai_ctx:
                AgtClipboardEvent.objects.create(
                    event_id=eid, device=device, user_id=uid, occurred_at=occ_dt,
                    content_kind=payload.get("content_kind", "text")[:8],
                    char_count=payload.get("char_count"), line_count=payload.get("line_count"),
                    file_count=payload.get("file_count"), matched_categories=payload.get("matched_categories", []),
                    regex_score=float(payload.get("regex_score", 0.0)), ml_score=float(payload.get("ml_score", 0.0)),
                    final_score=float(payload.get("final_score", 0.0)), risk_tier=tier,
                    foreground_app=str(payload.get("foreground_app", "unknown"))[:60],
                    foreground_class=str(payload.get("foreground_class", "unknown"))[:16],
                    ai_context=ai_ctx, ai_keyword=payload.get("ai_keyword"),
                    ruleset_version=int(payload.get("ruleset_version", 1)),
                    model_version=int(payload.get("model_version", 1))
                )

                # Rule AG-06: High-tier clipboard event with ai_context=True
                if tier == "high" and ai_ctx:
                    raise_agent_flag(uid, ev_date, "AG-06", "high", "T1115",
                                     f"High-risk sensitive content copied while AI app ({payload.get('foreground_app')}) was focused.")

                # Rule AG-07: 3 or more medium/high clipboard events within 10 minutes
                recent_cb_count = AgtClipboardEvent.objects.filter(
                    user_id=uid, risk_tier__in=["medium", "high"],
                    occurred_at__gte=occ_dt - timedelta(minutes=10), occurred_at__lte=occ_dt
                ).count()
                if recent_cb_count >= 3:
                    raise_agent_flag(uid, ev_date, "AG-07", "medium", "T1115",
                                     f"{recent_cb_count} medium/high-risk clipboard copies detected within 10 minutes.")

        elif etype == "app_session":
            if AgtAppSession.objects.filter(event_id=eid).exists():
                return "duplicate_ignored"
            AgtAppSession.objects.create(
                event_id=eid, device=device, user_id=uid,
                app_label=str(payload.get("app_label", "AI_App"))[:40],
                started_at=parse_dt(payload.get("started_at") or payload["occurred_at"]),
                ended_at=parse_dt(payload.get("ended_at") or payload["occurred_at"]),
                focus_seconds=int(payload.get("focus_seconds", 0))
            )

        elif etype == "agent_stop":
            AgtHealthAlert.objects.create(
                device=device, user_id=uid, alert_type="graceful_stop",
                severity="low", started_at=occ_dt, resolved_at=occ_dt,
                details={"reason": payload.get("reason", "normal_shutdown")}
            )

        elif etype == "agent_unclean_restart":
            AgtHealthAlert.objects.create(
                device=device, user_id=uid, alert_type="ungraceful_stop",
                severity="high", started_at=occ_dt,
                details={"reason": "Previous session left running marker without graceful stop"}
            )
            # Rule AG-09: Unclean restart within 30 minutes after a USB or high clipboard event
            recent_usb = AgtUsbEvent.objects.filter(
                user_id=uid, occurred_at__gte=occ_dt - timedelta(minutes=30), occurred_at__lte=occ_dt
            ).exists()
            recent_high_cb = AgtClipboardEvent.objects.filter(
                user_id=uid, risk_tier="high", occurred_at__gte=occ_dt - timedelta(minutes=30), occurred_at__lte=occ_dt
            ).exists()
            if recent_usb or recent_high_cb:
                raise_agent_flag(uid, ev_date, "AG-09", "high", "T1562.001",
                                 "Unclean agent restart or termination within 30 minutes of a USB or high-risk clipboard event.")

        update_daily_agg(uid, ev_date)
    return "committed"


def evaluate_heartbeat_gaps(now=None):
    """Server-side scheduled health monitor (Section 11 H2 & Rules AG-09, AG-10)."""
    now = now or timezone.now()
    for dev in ExtDevice.objects.filter(device_kind="agent", is_active=True):
        last_hb = AgtHeartbeat.objects.filter(device=dev).order_by("-received_at").first()
        if not last_hb:
            continue
        gap_seconds = (now - last_hb.received_at).total_seconds()
        if gap_seconds > 180:  # > 3 intervals of 60s
            AgtHealthAlert.objects.get_or_create(
                device=dev, user_id=dev.user_id, alert_type="heartbeat_gap", resolved_at__isnull=True,
                defaults={"severity": "medium", "started_at": now, "details": {"gap_seconds": int(gap_seconds)}}
            )
            # Rule AG-09: Heartbeat gap within 30m after USB or high clipboard event
            recent_usb = AgtUsbEvent.objects.filter(
                user_id=dev.user_id, occurred_at__gte=last_hb.received_at - timedelta(minutes=30)
            ).exists()
            recent_high_cb = AgtClipboardEvent.objects.filter(
                user_id=dev.user_id, risk_tier="high", occurred_at__gte=last_hb.received_at - timedelta(minutes=30)
            ).exists()
            if recent_usb or recent_high_cb:
                raise_agent_flag(dev.user_id, now.date(), "AG-09", "high", "T1562.001",
                                 "Heartbeat gap detected within 30 minutes of a USB or high-risk clipboard event.")

        if gap_seconds > 86400:  # > 1 working day (24h) -> Rule AG-10
            raise_agent_flag(dev.user_id, now.date(), "AG-10", "medium", "NONE",
                             "Endpoint agent silent for more than one full working day (coverage lost).")


def run_agent_worker():
    r = redis.Redis.from_url(getattr(settings, "REDIS_URL", "redis://127.0.0.1:6379/0"), decode_responses=True)
    try:
        r.xgroup_create(STREAM_NAME, GROUP_NAME, id="0", mkstream=True)
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise

    print(f"[*] Agent Worker listening on stream '{STREAM_NAME}' (group '{GROUP_NAME}')...")
    while True:
        try:
            entries = r.xreadgroup(GROUP_NAME, "agent_worker_1", {STREAM_NAME: ">"}, count=50, block=2000)
            if not entries:
                continue
            for _, messages in entries:
                for msg_id, fields in messages:
                    try:
                        payload = json.loads(fields.get("payload", "{}"))
                        status_str = process_single_agent_event(payload)
                        r.xack(STREAM_NAME, GROUP_NAME, msg_id)
                        print(f"[+] Agent Msg {msg_id} ({status_str}) -> ACKed")
                    except Exception as ex:
                        print(f"[!] Poison message {msg_id} routed to {DLQ_STREAM_NAME}: {ex}")
                        r.xadd(DLQ_STREAM_NAME, {"original_id": msg_id, "error": str(ex), "raw": fields.get("payload", "")})
                        r.xack(STREAM_NAME, GROUP_NAME, msg_id)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[!] Worker loop error: {e}")
            time.sleep(2)


if __name__ == "__main__":
    run_agent_worker()
