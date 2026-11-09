from django.db import models
from apps.events.models import ExtPasteEvent

class ExtAnalystFeedback(models.Model):
    event = models.ForeignKey(ExtPasteEvent, on_delete=models.CASCADE, db_column='event_id')
    analyst_id = models.CharField(max_length=64)
    verdict = models.CharField(max_length=16)  # true_positive or false_positive
    comment = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ext_analyst_feedback'
        constraints = [
            models.UniqueConstraint(fields=['event', 'analyst_id'], name='uq_feedback_event_analyst')
        ]