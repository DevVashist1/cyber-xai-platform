import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime
import django
import redis
from django.db import transaction
from django.db.models import F

# Setup Django environment
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BACKEND_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.events.models import ExtPasteEvent, ExtDailyPasteAgg
from apps.behavior.models import BehRuleFlag
from config.redis_client import get_redis_client

STREAM_NAME = "paste_events"
DLQ_STREAM_NAME = "paste_events_dlq"
GROUP_NAME = "backend_workers"
CONSUMER_NAME = "worker_1"
MAX_STREAM_LEN = 10000
MAX_RETRIES = 3


def setup_consumer_group(r):
    try:
        r.xgroup_create(STREAM_NAME, GROUP_NAME, id="0", mkstream=True)
        print(f"[*] Created Redis Consumer Group: {GROUP_NAME}")
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" in str(e):
            print(f"[*] Consumer Group '{GROUP_NAME}' already exists. Continuing...")
        else:
            raise e


def parse_payload(raw_payload):
    if isinstance(raw_payload, dict):
        return raw_payload
    try:
        return json.loads(raw_payload)
    except Exception:
        # Fallback for legacy str(dict) payloads
        import ast
        return ast.literal_eval(raw_payload)


def process_single_event(event_data):
    with transaction.atomic():
        # 1. Idempotent creation by unique event_id (Section 2.13 & 6.9 B4)
        occurred_str = event_data["occurred_at"]
        event_obj, created = ExtPasteEvent.objects.get_or_create(
            event_id=event_data["event_id"],
            defaults={
                "device_id": event_data["device_id"],
                "user_id": event_data["user_id"],
                "occurred_at": occurred_str,
                "site_domain": event_data["site_domain"],
                "event_type": event_data.get("event_type", "paste"),
                "content_length": event_data["content_length"],
                "line_count": event_data.get("line_count", 1),
                "file_extension": event_data.get("file_extension"),
                "matched_categories": event_data.get("matched_categories", []),
                "regex_score": event_data["regex_score"],
                "ml_score": event_data["ml_score"],
                "final_score": event_data["final_score"],
                "risk_tier": event_data["risk_tier"],
                "action": event_data["action"],
                "override_used": event_data.get("override_used", False),
                "override_reason": event_data.get("override_reason"),
                "content_hash": event_data.get("content_hash"),
                "ruleset_version": event_data.get("ruleset_version", 1),
                "model_version": event_data.get("model_version", 1),
            }
        )

        if not created:
            # If this is an override update for an already-logged event, update it
            if event_data.get("override_used") and not event_obj.override_used:
                event_obj.override_used = True
                event_obj.override_reason = event_data.get("override_reason")
                event_obj.save(update_fields=["override_used", "override_reason"])
            else:
                return "duplicate_ignored"

        # 2. Update Daily Paste Aggregates (Section 5.1 & 6.9 B5)
        event_date = datetime.fromisoformat(occurred_str.replace("Z", "+00:00")).date()
        agg, _ = ExtDailyPasteAgg.objects.get_or_create(
            user_id=event_data["user_id"],
            date=event_date
        )
        if event_data.get("event_type") == "upload":
            agg.upload_count = F("upload_count") + 1
        else:
            agg.paste_count = F("paste_count") + 1

        if event_data["risk_tier"] == "medium":
            agg.medium_count = F("medium_count") + 1
        elif event_data["risk_tier"] == "high":
            agg.high_count = F("high_count") + 1

        if event_data["action"] == "blocked":
            agg.blocked_count = F("blocked_count") + 1

        if event_data.get("override_used"):
            agg.override_count = F("override_count") + 1

        agg.save()

        # 3. Rule Engine Hook: Blocked-paste override creates a High severity BehRuleFlag (Section 7.7)
        if event_data.get("override_used") and event_data.get("risk_tier") == "high":
            BehRuleFlag.objects.create(
                user_id=event_data["user_id"],
                date=event_date,
                rule_id="RULE_BLOCKED_PASTE_OVERRIDE",
                severity="high",
                reason_text=(
                    f"User overrode a HIGH-risk blocked {event_data.get('event_type', 'paste')} "
                    f"on {event_data.get('site_domain')} (Reason: '{event_data.get('override_reason')}')"
                ),
            )

    return "committed"


def run_worker():
    r = get_redis_client()
    setup_consumer_group(r)
    retry_counts = {}

    print(f"[*] Worker '{CONSUMER_NAME}' listening on stream '{STREAM_NAME}' (DLQ: '{DLQ_STREAM_NAME}')...")

    while True:
        try:
            # Read new messages (>), or pending messages if recovering
            streams = r.xreadgroup(GROUP_NAME, CONSUMER_NAME, {STREAM_NAME: ">"}, count=20, block=2000)
            if not streams:
                continue

            for _, messages in streams:
                for message_id, data in messages:
                    payload_str = data.get("payload")
                    try:
                        event_data = parse_payload(payload_str)
                        result = process_single_event(event_data)
                        r.xack(STREAM_NAME, GROUP_NAME, message_id)
                        retry_counts.pop(message_id, None)
                        print(f"[+] Message {message_id} ({result}) -> ACKed")
                    except Exception as err:
                        retries = retry_counts.get(message_id, 0) + 1
                        retry_counts[message_id] = retries
                        print(f"[-] Error on {message_id} (Attempt {retries}/{MAX_RETRIES}): {err}")

                        if retries >= MAX_RETRIES:
                            # Move poison message to Dead-Letter Stream (Section 6.9 B4 & Test B-05)
                            r.xadd(DLQ_STREAM_NAME, {
                                "original_id": str(message_id),
                                "payload": str(payload_str),
                                "error": str(err),
                                "failed_at": datetime.utcnow().isoformat()
                            })
                            r.xack(STREAM_NAME, GROUP_NAME, message_id)
                            retry_counts.pop(message_id, None)
                            print(f"[!] Moved poison message {message_id} to DLQ '{DLQ_STREAM_NAME}'")

            # Approximate stream trimming so Redis memory stays bounded (Section 6.9 B4)
            r.xtrim(STREAM_NAME, maxlen=MAX_STREAM_LEN, approximate=True)

        except KeyboardInterrupt:
            print("\n[*] Stopping worker...")
            break
        except Exception as e:
            print(f"[-] Worker loop error: {e}")
            time.sleep(2)


if __name__ == "__main__":
    run_worker()