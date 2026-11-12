from django.urls import path
from .views import NetworkForecastView, NetworkAlertsView, NetworkActiveModelView, NetworkReplayControlView

urlpatterns = [
    path("forecast", NetworkForecastView.as_view(), name="net-forecast-no-slash"),
    path("forecast/", NetworkForecastView.as_view(), name="net-forecast"),
    path("alerts", NetworkAlertsView.as_view(), name="net-alerts-no-slash"),
    path("alerts/", NetworkAlertsView.as_view(), name="net-alerts"),
    path("model", NetworkActiveModelView.as_view(), name="net-model-no-slash"),
    path("model/", NetworkActiveModelView.as_view(), name="net-model"),
    path("replay", NetworkReplayControlView.as_view(), name="net-replay-no-slash"),
    path("replay/", NetworkReplayControlView.as_view(), name="net-replay"),
]
