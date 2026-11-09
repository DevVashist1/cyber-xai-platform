from django.db import models

class UserDailyActivity(models.Model):
    row_id = models.BigIntegerField(primary_key=True)
    user_id = models.CharField(max_length=32)
    date = models.DateField()
    department = models.CharField(max_length=100)
    logon_count = models.IntegerField()
    after_hours_logons = models.IntegerField()
    distinct_pcs = models.IntegerField()
    usb_connects = models.IntegerField()
    after_hours_usb_connects = models.IntegerField()
    files_copied = models.IntegerField()
    emails_sent = models.IntegerField()
    external_emails = models.IntegerField()
    emails_with_attachments = models.IntegerField()
    websites_visited = models.IntegerField()
    is_malicious = models.SmallIntegerField()

    class Meta:
        managed = False
        db_table = 'user_daily_activity'

class BehModelRegistry(models.Model):
    model_version = models.IntegerField(primary_key=True)
    trained_at = models.DateTimeField(auto_now_add=True)
    algorithm = models.CharField(max_length=64)
    feature_list = models.JSONField()
    date_ranges = models.JSONField()
    metrics = models.JSONField()
    file_reference = models.CharField(max_length=255)
    is_active = models.BooleanField(default=False)

    class Meta:
        db_table = 'beh_model_registry'

class BehFeatureMatrix(models.Model):
    user_id = models.CharField(max_length=32)
    date = models.DateField()
    model_version = models.IntegerField()
    features = models.JSONField()

    class Meta:
        db_table = 'beh_feature_matrix'
        constraints = [
            models.UniqueConstraint(fields=['user_id', 'date', 'model_version'], name='uq_beh_feat_user_date_ver')
        ]

class BehDailyScore(models.Model):
    user_id = models.CharField(max_length=32)
    date = models.DateField()
    model_version = models.IntegerField()
    probability = models.FloatField()
    rank_in_day = models.IntegerField()

    class Meta:
        db_table = 'beh_daily_score'
        constraints = [
            models.UniqueConstraint(fields=['user_id', 'date', 'model_version'], name='uq_beh_score_user_date_ver')
        ]
        indexes = [
            models.Index(fields=['date', '-probability']),
        ]

class BehRuleFlag(models.Model):
    user_id = models.CharField(max_length=32)
    date = models.DateField()
    rule_id = models.CharField(max_length=64)
    severity = models.CharField(max_length=16)
    reason_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'beh_rule_flag'
        indexes = [
            models.Index(fields=['user_id', 'date']),
            models.Index(fields=['date']),
        ]