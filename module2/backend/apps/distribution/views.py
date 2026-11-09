from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from apps.distribution.models import ExtRulesetVersion, ExtModelVersion


class RulesConfigView(APIView):
    def get(self, request):
        current = int(request.query_params.get("current", 0))
        active_rules = ExtRulesetVersion.objects.filter(is_active=True).order_by("-version").first()

        if not active_rules or active_rules.version <= current:
            return Response({"status": "not_modified", "version": current}, status=status.HTTP_200_OK)

        return Response({
            "status": "updated",
            "version": active_rules.version,
            "content": active_rules.content,
        }, status=status.HTTP_200_OK)


class ModelConfigView(APIView):
    def get(self, request):
        current = int(request.query_params.get("current", 0))
        active_model = ExtModelVersion.objects.filter(is_active=True).order_by("-version").first()

        if not active_model or active_model.version <= current:
            return Response({"status": "not_modified", "version": current}, status=status.HTTP_200_OK)

        return Response({
            "status": "updated",
            "version": active_model.version,
            "weights_json": active_model.weights_json,
            "feature_names": active_model.feature_names,
        }, status=status.HTTP_200_OK)