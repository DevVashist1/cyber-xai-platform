import uuid
from django.db import models

class ExtDevice(models.Model):
    device_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.CharField(max_length=32, db_index=True)
    device_kind = models.CharField(max_length=12, default="extension")  # extension or agent
    token_hash = models.CharField(max_length=64, unique=True)
    os_user_hash = models.CharField(max_length=64, null=True, blank=True)
    hostname_hash = models.CharField(max_length=64, null=True, blank=True)
    os_version = models.CharField(max_length=40, null=True, blank=True)
    client_version = models.CharField(max_length=16, default="1.0.0")
    registered_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    @property
    def extension_version(self):
        return self.client_version

    @extension_version.setter
    def extension_version(self, val):
        self.client_version = val

    class Meta:
        db_table = "ext_device"
