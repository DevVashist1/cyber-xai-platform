import hashlib
import secrets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from .models import ExtDevice

class DeviceRegisterView(APIView):
    def post(self, request):
        enrollment_code = request.data.get("enrollment_code")
        user_id = request.data.get("user_id")
        extension_version = request.data.get("extension_version", "1.0.0")

        if enrollment_code != settings.ENROLLMENT_CODE:
            return Response({"error": "Invalid enrollment code"}, status=status.HTTP_403_FORBIDDEN)
        
        if not user_id:
            return Response({"error": "user_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Generate a raw device token (shown once to the client)
        raw_token = secrets.token_hex(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        device = ExtDevice.objects.create(
            user_id=user_id,
            token_hash=token_hash,
            extension_version=extension_version
        )

        return Response({
            "device_id": str(device.device_id),
            "device_token": raw_token  # Client must save this securely
        }, status=status.HTTP_201_CREATED)