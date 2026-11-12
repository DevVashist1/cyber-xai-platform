from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("api/v1/network/", include("module4.backend.apps.network.urls")),
    path('api/v1/', include('apps.agent_ingest.urls')),
    path('admin/', admin.site.urls),
    path('api/v1/devices/', include('apps.devices.urls')),
    path('api/v1/events/', include('apps.events.urls')),
    path('api/v1/analyst/', include('apps.feedback.urls')),
    path('api/v1/config/', include('apps.distribution.urls')),
    path('api/v1/behavior/', include('apps.behavior.urls')),
]