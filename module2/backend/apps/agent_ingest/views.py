import json
import hashlib
import redis
from datetime import datetime, timezone as dt_tz
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from apps.devices.models import ExtDevice
from .models import (
    AgtUsbEvent, AgtFileTransferEvent, AgtClipboardEvent,
    AgtAppSession, AgtHeartbeat, AgtHealthAlert, AgtConfigVersion, AgtDailyAgg
)

class DeviceTokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None
        token = auth_header.split(" ", 1)[1].strip()
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        try:
            device = ExtDevice.objects.get(token_hash=token_hash, is_active=True)
            return (device, None)
        except ExtDevice.DoesNotExist:
            raise AuthenticationFailed("Invalid or inactive device token")

def get_redis_client():
    return redis.Redis.from_url(getattr(settings, "REDIS_URL", "redis://127.0.0.1:6379/0"), decode_responses=True)

VALID_EVENT_TYPES = {
    "usb_connect", "usb_disconnect", "file_transfer",
    "clipboard", "app_session", "agent_stop", "agent_unclean_restart"
}

class AgentEventsIngestView(APIView):
    authentication_classes = [DeviceTokenAuthentication]

    def post(self, request):
        if not isinstance(request.user, ExtDevice):
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        device = request.user
        raw_body = request.body or b""
        if len(raw_body) > 512 * 1024:
            return Response({"error": "Payload exceeds 512KB cap"}, status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

        events = request.data.get("events")
        if not isinstance(events, list) or len(events) == 0 or len(events) > 100:
            return Response({"error": "Must provide 'events' list of 1 to 100 items"}, status=status.HTTP_400_BAD_REQUEST)

        forbidden_keys = {"raw_text", "clipboard_text", "file_name", "filenames", "window_title"}
        validated = []
        for ev in events:
            if not isinstance(ev, dict):
                return Response({"error": "Each event must be an object"}, status=status.HTTP_400_BAD_REQUEST)
            if forbidden_keys.intersection(ev.keys()):
                return Response({"error": "Privacy violation: forbidden content field present"}, status=status.HTTP_400_BAD_REQUEST)
            etype = ev.get("event_type")
            eid = ev.get("event_id")
            occ = ev.get("occurred_at")
            if etype not in VALID_EVENT_TYPES or not eid or not occ:
                return Response({"error": f"Invalid event schema for event_id={eid}"}, status=status.HTTP_400_BAD_REQUEST)

            ev["device_id"] = str(device.device_id)
            ev["user_id"] = device.user_id
            validated.append(ev)

        r = get_redis_client()
        pipe = r.pipeline()
        for ev in validated:
            pipe.xadd("agent_events", {"payload": json.dumps(ev)})
        pipe.execute()

        return Response({"accepted": len(validated)}, status=status.HTTP_202_ACCEPTED)


class AgentHeartbeatView(APIView):
    authentication_classes = [DeviceTokenAuthentication]

    def post(self, request):
        if not isinstance(request.user, ExtDevice):
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        device = request.user
        data = request.data
        now = timezone.now()

        occ_str = data.get("occurred_at")
        occ_dt = parse_datetime(occ_str) if occ_str else now
        if occ_dt and timezone.is_naive(occ_dt):
            occ_dt = timezone.make_aware(occ_dt, dt_tz.utc)

        skew_sec = int(abs((now - (occ_dt or now)).total_seconds()))

        started_str = data.get("agent_started_at")
        started_dt = parse_datetime(started_str) if started_str else now
        if started_dt and timezone.is_naive(started_dt):
            started_dt = timezone.make_aware(started_dt, dt_tz.utc)

        hb = AgtHeartbeat.objects.create(
            device=device,
            agent_started_at=started_dt or now,
            client_version=str(data.get("client_version", "1.0.0"))[:16],
            queue_depth=int(data.get("queue_depth", 0)),
            dropped_events_total=int(data.get("dropped_events_total", 0)),
            watcher_status=data.get("watcher_status", {}),
            events_sent_since_last=int(data.get("events_sent_since_last", 0)),
            low_risk_clipboard_count=int(data.get("low_risk_clipboard_count", 0)),
            cpu_pct=float(data.get("cpu_pct", 0.0)),
            mem_mb=float(data.get("mem_mb", 0.0)),
            config_version=int(data.get("config_version", 1)),
            clock_skew_seconds=skew_sec
        )

        AgtHealthAlert.objects.filter(
            device=device, alert_type="heartbeat_gap", resolved_at__isnull=True
        ).update(resolved_at=now)

        if skew_sec > 300:
            AgtHealthAlert.objects.create(
                device=device, user_id=device.user_id, alert_type="clock_skew",
                severity="high", started_at=now,
                details={"clock_skew_seconds": skew_sec, "reason": "Device clock differs from server by >300s"}
            )

        if hb.queue_depth > 1000:
            AgtHealthAlert.objects.create(
                device=device, user_id=device.user_id, alert_type="queue_backlog",
                severity="medium", started_at=now,
                details={"queue_depth": hb.queue_depth}
            )

        for w_name, w_state in (hb.watcher_status or {}).items():
            if str(w_state).startswith("error"):
                AgtHealthAlert.objects.create(
                    device=device, user_id=device.user_id, alert_type="watcher_failure",
                    severity="medium", started_at=now,
                    details={"watcher": w_name, "status": w_state}
                )

        return Response({"status": "ok", "clock_skew_seconds": skew_sec}, status=status.HTTP_200_OK)


class AgentConfigView(APIView):
    authentication_classes = [DeviceTokenAuthentication]

    def get(self, request):
        if not isinstance(request.user, ExtDevice):
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        current_ver = int(request.query_params.get("current", 0))
        active_cfg = AgtConfigVersion.objects.filter(is_active=True).order_by("-version").first()
        if not active_cfg or active_cfg.version == current_ver:
            return Response({"status": "not_modified", "version": current_ver}, status=status.HTTP_200_OK)
        return Response({
            "version": active_cfg.version,
            "content": active_cfg.content
        }, status=status.HTTP_200_OK)


class AgentReadListView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request, resource):
        user_id = request.query_params.get("user_id")
        if resource == "usb":
            qs = AgtUsbEvent.objects.all().order_by("-occurred_at")
            if user_id: qs = qs.filter(user_id=user_id)
            return Response(list(qs[:100].values()))
        elif resource == "transfers":
            qs = AgtFileTransferEvent.objects.all().order_by("-session_start")
            if user_id: qs = qs.filter(user_id=user_id)
            return Response(list(qs[:100].values()))
        elif resource == "clipboard":
            qs = AgtClipboardEvent.objects.all().order_by("-occurred_at")
            if user_id: qs = qs.filter(user_id=user_id)
            return Response(list(qs[:100].values()))
        elif resource == "health":
            alerts = list(AgtHealthAlert.objects.all().order_by("-started_at")[:50].values())
            aggs = list(AgtDailyAgg.objects.all().order_by("-date")[:50].values())
            return Response({"alerts": alerts, "daily_agg": aggs})
        return Response({"error": "Unknown resource"}, status=status.HTTP_404_NOT_FOUND)
