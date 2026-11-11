from django.urls import path
from .views import AgentEventsIngestView, AgentHeartbeatView, AgentConfigView, AgentReadListView

urlpatterns = [
    path("agent/events", AgentEventsIngestView.as_view()),
    path("agent/events/", AgentEventsIngestView.as_view()),
    path("agent/heartbeat", AgentHeartbeatView.as_view()),
    path("agent/heartbeat/", AgentHeartbeatView.as_view()),
    path("config/agent", AgentConfigView.as_view()),
    path("config/agent/", AgentConfigView.as_view()),
    path("agent/<str:resource>", AgentReadListView.as_view()),
    path("agent/<str:resource>/", AgentReadListView.as_view()),
]
