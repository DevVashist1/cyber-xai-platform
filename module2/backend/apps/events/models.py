from django.db import models
from apps.devices.models import ExtDevice

class ExtPasteEvent(models.Model):
    event_id = models.UUIDField(primary_key=True)
    device = models.ForeignKey(ExtDevice, on_delete=models.CASCADE, db_column='device_id')
    user_id = models.CharField(max_length=32)
    occurred_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)
    site_domain = models.CharField(max_length=100)
    event_type = models.CharField(max_length=12)
    content_length = models.IntegerField()
    line_count = models.IntegerField()
    file_extension = models.CharField(max_length=16, null=True, blank=True)
    matched_categories = models.JSONField(default=list)
    regex_score = models.FloatField()
    ml_score = models.FloatField()
    final_score = models.FloatField()
    risk_tier = models.CharField(max_length=8)
    action = models.CharField(max_length=8)
    override_used = models.BooleanField(default=False)
    override_reason = models.TextField(null=True, blank=True)
    content_hash = models.CharField(max_length=64, null=True, blank=True)
    ruleset_version = models.IntegerField()
    model_version = models.IntegerField()

    class Meta:
        db_table = 'ext_paste_event'
        indexes = [
            models.Index(fields=['user_id', 'occurred_at']),
            models.Index(fields=['occurred_at']),
            models.Index(fields=['risk_tier', 'occurred_at']),
        ]

class ExtDailyPasteAgg(models.Model):
    user_id = models.CharField(max_length=32)
    date = models.DateField()
    paste_count = models.IntegerField(default=0)
    upload_count = models.IntegerField(default=0)
    medium_count = models.IntegerField(default=0)
    high_count = models.IntegerField(default=0)
    blocked_count = models.IntegerField(default=0)
    override_count = models.IntegerField(default=0)

    class Meta:
        db_table = 'ext_daily_paste_agg'
        constraints = [
            models.UniqueConstraint(fields=['user_id', 'date'], name='uq_ext_daily_paste_user_date')
        ]