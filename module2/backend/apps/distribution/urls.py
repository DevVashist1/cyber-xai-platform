from django.urls import path
from apps.distribution.views import RulesConfigView, ModelConfigView

urlpatterns = [
    path("rules", RulesConfigView.as_view(), name="config-rules"),
    path("rules/", RulesConfigView.as_view(), name="config-rules-slash"),
    path("model", ModelConfigView.as_view(), name="config-model"),
    path("model/", ModelConfigView.as_view(), name="config-model-slash"),
]