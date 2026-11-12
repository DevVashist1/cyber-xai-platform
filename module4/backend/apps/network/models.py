from django.db import models

class NetModelRegistry(models.Model):
    model_version = models.CharField(max_length=64, primary_key=True)
    run_id = models.CharField(max_length=64)
    model_type = models.CharField(max_length=32)
    file_ref = models.CharField(max_length=255)
    feature_list = models.JSONField()
    window_size_sec = models.IntegerField()
    horizon_k = models.IntegerField()
    calibrator = models.JSONField()
    thresholds = models.JSONField()
    hysteresis = models.JSONField()
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "net_model_registry"
