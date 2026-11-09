from django.urls import path
from .views import EventIngestionView

urlpatterns = [
    path('', EventIngestionView.as_view(), name='event-ingest'),
]