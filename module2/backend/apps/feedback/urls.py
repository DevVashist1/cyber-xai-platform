from django.urls import path
from .views import HighRiskEventsView, AnalystFeedbackView, UserRiskLeaderboardView

urlpatterns = [
    path('events/high-risk/', HighRiskEventsView.as_view(), name='high-risk-events'),
    path('feedback/', AnalystFeedbackView.as_view(), name='analyst-feedback'),
    path('leaderboard/', UserRiskLeaderboardView.as_view(), name='risk-leaderboard'),
]