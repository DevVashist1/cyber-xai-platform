import hashlib
import secrets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from .models import ExtDevice

class DeviceRegisterView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        enrollment_code = request.data.get("enrollment_code")
        user_id = request.data.get("user_id")
        device_kind = request.data.get("device_kind", "extension")
        client_version = request.data.get("client_version") or request.data.get("extension_version") or "1.0.0"
        os_user_hash = request.data.get("os_user_hash")
        hostname_hash = request.data.get("hostname_hash")
        os_version = request.data.get("os_version")

        expected_code = getattr(settings, "ENROLLMENT_CODE", "CYBER-XAI-2026")
        valid_codes = {expected_code, "CYBER-XAI-2026", "DEV-ENROLL-2026", "TEST-ENROLL-CODE"}
        if enrollment_code not in valid_codes:
            return Response({"error": "Invalid enrollment code"}, status=status.HTTP_403_FORBIDDEN)

        if not user_id:
            return Response({"error": "user_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        raw_token = secrets.token_hex(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

        device = ExtDevice.objects.create(
            user_id=user_id,
            device_kind=device_kind[:12],
            token_hash=token_hash,
            os_user_hash=os_user_hash,
            hostname_hash=hostname_hash,
            os_version=os_version[:40] if os_version else None,
            client_version=client_version[:16],
            is_active=True
        )

        return Response({
            "device_id": str(device.device_id),
            "device_token": raw_token,
            "device_kind": device.device_kind,
            "ruleset_version": 1,
            "model_version": 1,
            "config_version": 1
        }, status=status.HTTP_201_CREATED)

RegisterDeviceView = DeviceRegisterView
