from django.db import models

class ExtRulesetVersion(models.Model):
    version = models.IntegerField(primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(max_length=64)
    content = models.JSONField()
    is_active = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'ext_ruleset_version'

class ExtModelVersion(models.Model):
    version = models.IntegerField(primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True)
    parent_version = models.IntegerField(null=True, blank=True)
    weights_json = models.JSONField()
    feature_names = models.JSONField()
    training_set_size = models.IntegerField()
    golden_set_metrics = models.JSONField()
    is_active = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'ext_model_version'