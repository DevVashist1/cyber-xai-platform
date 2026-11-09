from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from apps.behavior.models import BehDailyScore, BehRuleFlag

class BehaviorScoresView(APIView):
    def get(self, request):
        scores = BehDailyScore.objects.order_by('-date', 'rank_in_day')[:100]
        data = [{
            "user_id": s.user_id,
            "date": str(s.date),
            "model_version": s.model_version,
            "probability": s.probability,
            "rank_in_day": s.rank_in_day
        } for s in scores]
        return Response(data, status=status.HTTP_200_OK)

class RuleFlagsView(APIView):
    def get(self, request):
        flags = BehRuleFlag.objects.order_by('-created_at')[:100]
        data = [{
            "user_id": f.user_id,
            "date": str(f.date),
            "rule_id": f.rule_id,
            "severity": f.severity,
            "reason_text": f.reason_text,
            "created_at": str(f.created_at)
        } for f in flags]
        return Response(data, status=status.HTTP_200_OK)