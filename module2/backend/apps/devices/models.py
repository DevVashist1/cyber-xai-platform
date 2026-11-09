import uuid
from django.db import models

class ExtDevice(models.Model):
    device_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.CharField(max_length=32, db_index=True)
    token_hash = models.CharField(max_length=64)
    registered_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    extension_version = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'ext_device'