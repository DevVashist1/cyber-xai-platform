import uuid
from django.db import models
from apps.devices.models import ExtDevice

class AgtUsbEvent(models.Model):
    event_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(ExtDevice, on_delete=models.CASCADE, db_column="device_id")
    user_id = models.CharField(max_length=32)
    occurred_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)
    event_type = models.CharField(max_length=12)  # connect, disconnect
    device_class = models.CharField(max_length=16, default="mass_storage")  # mass_storage, mtp, other
    drive_letter = models.CharField(max_length=3, null=True, blank=True)
    volume_serial_hash = models.CharField(max_length=64, null=True, blank=True)
    usb_vid_pid = models.CharField(max_length=9, null=True, blank=True)
    capacity_gb = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    fs_type = models.CharField(max_length=10, null=True, blank=True)
    is_encrypted = models.BooleanField(null=True, blank=True)
    is_first_seen_for_user = models.BooleanField(default=False)
    is_after_hours = models.BooleanField(default=False)

    class Meta:
        db_table = "agt_usb_event"
        indexes = [
            models.Index(fields=["user_id", "occurred_at"]),
            models.Index(fields=["volume_serial_hash"]),
        ]

class AgtFileTransferEvent(models.Model):
    event_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(ExtDevice, on_delete=models.CASCADE, db_column="device_id")
    user_id = models.CharField(max_length=32)
    session_start = models.DateTimeField()
    session_end = models.DateTimeField()
    volume_serial_hash = models.CharField(max_length=64)
    usb_connect_event_id = models.UUIDField(null=True, blank=True)
    file_count = models.IntegerField(default=0)
    total_bytes = models.BigIntegerField(default=0)
    max_file_bytes = models.BigIntegerField(default=0)
    ext_histogram = models.JSONField(default=dict)
    sensitive_ext_count = models.IntegerField(default=0)
    archive_count = models.IntegerField(default=0)
    duration_seconds = models.IntegerField(default=0)
    is_after_hours = models.BooleanField(default=False)
    is_partial = models.BooleanField(default=False)

    class Meta:
        db_table = "agt_file_transfer_event"
        indexes = [models.Index(fields=["user_id", "session_start"])]

class AgtClipboardEvent(models.Model):
    event_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(ExtDevice, on_delete=models.CASCADE, db_column="device_id")
    user_id = models.CharField(max_length=32)
    occurred_at = models.DateTimeField()
    content_kind = models.CharField(max_length=8)  # text, files, image, other
    char_count = models.IntegerField(null=True, blank=True)
    line_count = models.IntegerField(null=True, blank=True)
    file_count = models.IntegerField(null=True, blank=True)
    matched_categories = models.JSONField(default=list)
    regex_score = models.FloatField(default=0.0)
    ml_score = models.FloatField(default=0.0)
    final_score = models.FloatField(default=0.0)
    risk_tier = models.CharField(max_length=8, default="low")  # low, medium, high
    foreground_app = models.CharField(max_length=60, default="unknown")
    foreground_class = models.CharField(max_length=16, default="unknown")
    ai_context = models.BooleanField(default=False)
    ai_keyword = models.CharField(max_length=40, null=True, blank=True)
    ruleset_version = models.IntegerField(default=1)
    model_version = models.IntegerField(default=1)

    class Meta:
        db_table = "agt_clipboard_event"
        indexes = [models.Index(fields=["user_id", "occurred_at"])]

class AgtAppSession(models.Model):
    event_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(ExtDevice, on_delete=models.CASCADE, db_column="device_id")
    user_id = models.CharField(max_length=32)
    app_label = models.CharField(max_length=40)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField()
    focus_seconds = models.IntegerField(default=0)

    class Meta:
        db_table = "agt_app_session"
        indexes = [models.Index(fields=["user_id", "started_at"])]

class AgtHeartbeat(models.Model):
    id = models.BigAutoField(primary_key=True)
    device = models.ForeignKey(ExtDevice, on_delete=models.CASCADE, db_column="device_id")
    received_at = models.DateTimeField(auto_now_add=True)
    agent_started_at = models.DateTimeField()
    client_version = models.CharField(max_length=16, default="1.0.0")
    queue_depth = models.IntegerField(default=0)
    dropped_events_total = models.IntegerField(default=0)
    watcher_status = models.JSONField(default=dict)
    events_sent_since_last = models.IntegerField(default=0)
    low_risk_clipboard_count = models.IntegerField(default=0)
    cpu_pct = models.FloatField(default=0.0)
    mem_mb = models.FloatField(default=0.0)
    config_version = models.IntegerField(default=1)
    clock_skew_seconds = models.IntegerField(default=0)

    class Meta:
        db_table = "agt_heartbeat"
        indexes = [models.Index(fields=["device", "received_at"])]

class AgtHealthAlert(models.Model):
    id = models.BigAutoField(primary_key=True)
    device = models.ForeignKey(ExtDevice, on_delete=models.CASCADE, db_column="device_id")
    user_id = models.CharField(max_length=32)
    alert_type = models.CharField(max_length=32)  # heartbeat_gap, ungraceful_stop, watcher_failure, clock_skew, queue_backlog
    severity = models.CharField(max_length=8, default="medium")
    started_at = models.DateTimeField()
    resolved_at = models.DateTimeField(null=True, blank=True)
    details = models.JSONField(default=dict)

    class Meta:
        db_table = "agt_health_alert"
        indexes = [models.Index(fields=["user_id", "started_at"])]

class AgtConfigVersion(models.Model):
    version = models.IntegerField(primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True)
    content = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "agt_config_version"

class AgtDailyAgg(models.Model):
    user_id = models.CharField(max_length=32)
    date = models.DateField()
    usb_connects = models.IntegerField(default=0)
    after_hours_usb_connects = models.IntegerField(default=0)
    distinct_usb_devices = models.IntegerField(default=0)
    files_copied_to_usb = models.IntegerField(default=0)
    bytes_copied_to_usb = models.BigIntegerField(default=0)
    sensitive_ext_files_to_usb = models.IntegerField(default=0)
    clipboard_medium_count = models.IntegerField(default=0)
    clipboard_high_count = models.IntegerField(default=0)
    ai_context_clipboard_count = models.IntegerField(default=0)
    ai_app_focus_minutes = models.IntegerField(default=0)
    agent_online_minutes = models.IntegerField(default=0)
    agent_gap_count = models.IntegerField(default=0)

    class Meta:
        db_table = "agt_daily_agg"
        unique_together = (("user_id", "date"),)
