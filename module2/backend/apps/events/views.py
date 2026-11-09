import hashlib
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from apps.devices.models import ExtDevice
from config.redis_client import get_redis_client

class EventIngestionView(APIView):
    def post(self, request):
        # 1. Authenticate via Device Token in Authorization header
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return Response({"error": "Missing or invalid bearer token"}, status=status.HTTP_401_UNAUTHORIZED)
        
        raw_token = auth_header.split(" ")[1]
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        try:
            device = ExtDevice.objects.get(token_hash=token_hash, is_active=True)
        except ExtDevice.DoesNotExist:
            return Response({"error": "Invalid or revoked device token"}, status=status.HTTP_403_FORBIDDEN)

        # 2. Extract event data payload from extension
        event_data = request.data
        event_data["device_id"] = str(device.device_id)
        event_data["user_id"] = device.user_id

        # 3. Push immediately to Redis Stream (paste_events) for async processing
        try:
            r = get_redis_client()
            # XADD streams data into Redis stream buffer
            r.xadd("paste_events", {"payload": str(event_data)})
        except Exception as e:
            return Response({"error": f"Failed to queue event: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"status": "accepted"}, status=status.HTTP_202_ACCEPTED)