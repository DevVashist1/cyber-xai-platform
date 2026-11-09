from django.urls import path
from apps.behavior.views import BehaviorScoresView, RuleFlagsView

urlpatterns = [
    path('scores/', BehaviorScoresView.as_view(), name='behavior-scores'),
    path('flags/', RuleFlagsView.as_view(), name='behavior-flags'),
]