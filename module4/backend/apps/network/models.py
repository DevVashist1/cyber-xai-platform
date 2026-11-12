from django.db import models

class NetWindowBase(models.Model):
    window_size_sec = models.IntegerField()
    window_start = models.DateTimeField(primary_key=True)
    window_end = models.DateTimeField()
    source_day = models.DateField()
    segment_id = models.IntegerField()
    flow_count = models.IntegerField()
    attack_flow_count = models.IntegerField()
    attack_share = models.FloatField()
    family_counts = models.JSONField()
    class Meta:
        managed = False
        db_table = "net_window_base"

class NetFeatureMatrix(models.Model):
    model_version = models.CharField(max_length=64)
    window_end = models.DateTimeField(primary_key=True)
    window_size_sec = models.IntegerField()
    source_day = models.DateField()
    segment_id = models.IntegerField()
    split_role = models.CharField(max_length=16)
    y = models.IntegerField()
    onset_flag = models.BooleanField()
    is_calm = models.BooleanField()
    features_json = models.JSONField()
    class Meta:
        managed = False
        db_table = "net_feature_matrix"

class NetSurgeEpisode(models.Model):
    episode_id = models.CharField(max_length=64, primary_key=True)
    config_id = models.CharField(max_length=64)
    window_size_sec = models.IntegerField()
    source_day = models.DateField()
    start_window = models.DateTimeField()
    end_window = models.DateTimeField()
    n_windows = models.IntegerField()
    peak_attack_share = models.FloatField()
    families = models.JSONField()
    class Meta:
        managed = False
        db_table = "net_surge_episode"

class NetExperimentRun(models.Model):
    run_id = models.CharField(max_length=64, primary_key=True)
    created_at = models.DateTimeField()
    git_commit = models.CharField(max_length=40)
    seed = models.IntegerField()
    window_size_sec = models.IntegerField()
    horizon_k = models.IntegerField()
    share_threshold = models.FloatField()
    flow_floor = models.IntegerField()
    split_scheme = models.CharField(max_length=32)
    training_regime = models.CharField(max_length=32)
    feature_set = models.CharField(max_length=32)
    model_type = models.CharField(max_length=32)
    params = models.JSONField()
    library_versions = models.JSONField()
    train_range = models.CharField(max_length=128)
    val_range = models.CharField(max_length=128)
    test_range = models.CharField(max_length=128)
    val_metrics = models.JSONField()
    test_metrics = models.JSONField(null=True)
    notes = models.TextField(null=True)
    class Meta:
        managed = False
        db_table = "net_experiment_run"

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

class NetForecast(models.Model):
    replay_run_id = models.CharField(max_length=64)
    model_version = models.CharField(max_length=64)
    window_end = models.DateTimeField(primary_key=True)
    raw_score = models.FloatField()
    calibrated_prob = models.FloatField()
    level = models.SmallIntegerField()
    level_reason = models.TextField()
    horizon_k = models.SmallIntegerField()
    actual_surge_in_horizon = models.BooleanField(null=True)
    created_at = models.DateTimeField()
    class Meta:
        managed = False
        db_table = "net_forecast"

class NetAlertEpisode(models.Model):
    episode_id = models.CharField(max_length=64, primary_key=True)
    replay_run_id = models.CharField(max_length=64)
    model_version = models.CharField(max_length=64)
    max_level = models.SmallIntegerField()
    start_window = models.DateTimeField()
    end_window = models.DateTimeField()
    peak_prob = models.FloatField()
    status = models.CharField(max_length=16)
    matched_surge_episode_id = models.CharField(max_length=64, null=True)
    class Meta:
        managed = False
        db_table = "net_alert_episode"

class NetFeatureDictionary(models.Model):
    feature_name = models.CharField(max_length=64, primary_key=True)
    display_name = models.CharField(max_length=128)
    feature_group = models.CharField(max_length=32)
    description = models.TextField()
    direction_hint = models.CharField(max_length=64)
    class Meta:
        managed = False
        db_table = "net_feature_dictionary"
