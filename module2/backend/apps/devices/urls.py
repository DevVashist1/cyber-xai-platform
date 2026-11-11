from django.urls import path
from .views import DeviceRegisterView

urlpatterns = [
    path("register", DeviceRegisterView.as_view(), name="device-register-no-slash"),
    path("register/", DeviceRegisterView.as_view(), name="device-register"),
]
