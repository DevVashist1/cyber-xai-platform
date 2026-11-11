from django.db import models

class UserDailyActivity(models.Model):
    user_id = models.CharField(max_length=64, primary_key=True)
    date = models.DateField()
    logon_count = models.IntegerField(default=0)
    after_hours_logons = models.IntegerField(default=0)
    usb_connects = models.IntegerField(default=0)
    files_copied = models.IntegerField(default=0)
    emails_sent = models.IntegerField(default=0)
    websites_visited = models.IntegerField(default=0)
    department = models.CharField(max_length=64, null=True, blank=True)
    is_malicious = models.IntegerField(default=0)

    class Meta:
        managed = False
        db_table = "user_daily_activity"

class BehFeatureMatrix(models.Model):
    user_id = models.CharField(max_length=32)
    date = models.DateField()
    model_version = models.IntegerField(default=1)
    features = models.JSONField(default=dict)

    class Meta:
        db_table = "beh_feature_matrix"
        unique_together = (("user_id", "date", "model_version"),)

class BehModelRegistry(models.Model):
    model_version = models.IntegerField(primary_key=True)
    trained_at = models.DateTimeField(auto_now_add=True)
    algorithm = models.CharField(max_length=32)
    feature_list = models.JSONField(default=list)
    date_ranges = models.JSONField(default=dict)
    metrics = models.JSONField(default=dict)
    file_reference = models.CharField(max_length=256)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "beh_model_registry"

class BehDailyScore(models.Model):
    user_id = models.CharField(max_length=32)
    date = models.DateField()
    model_version = models.IntegerField(default=1)
    probability = models.FloatField()
    rank_in_day = models.IntegerField(default=1)

    class Meta:
        db_table = "beh_daily_score"
        unique_together = (("user_id", "date", "model_version"),)
        indexes = [models.Index(fields=["date", "-probability"])]

class BehRuleFlag(models.Model):
    user_id = models.CharField(max_length=32, db_index=True)
    date = models.DateField(db_index=True)
    rule_id = models.CharField(max_length=32)
    severity = models.CharField(max_length=8)
    source_module = models.CharField(max_length=10, default="module2")
    mitre_technique = models.CharField(max_length=32, null=True, blank=True)
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "beh_rule_flag"
        indexes = [models.Index(fields=["user_id", "date"])]
