from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from apps.events.models import ExtPasteEvent
from apps.behavior.models import BehDailyScore
from .models import ExtAnalystFeedback

class HighRiskEventsView(APIView):
    def get(self, request):
        # Fetch recent high or medium risk paste events for analyst review
        events = ExtPasteEvent.objects.filter(risk_tier__in=['high', 'medium']).order_by('-occurred_at')[:50]
        data = [{
            "event_id": str(e.event_id),
            "user_id": e.user_id,
            "occurred_at": str(e.occurred_at),
            "site_domain": e.site_domain,
            "content_length": e.content_length,
            "risk_tier": e.risk_tier,
            "final_score": e.final_score,
            "action": e.action
        } for e in events]
        return Response(data, status=status.HTTP_200_OK)

class AnalystFeedbackView(APIView):
    def post(self, request):
        event_id = request.data.get("event_id")
        analyst_id = request.data.get("analyst_id", "analyst_1")
        verdict = request.data.get("verdict")  # true_positive or false_positive
        comment = request.data.get("comment", "")

        if not event_id or verdict not in ['true_positive', 'false_positive']:
            return Response({"error": "event_id and valid verdict (true_positive/false_positive) are required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            event = ExtPasteEvent.objects.get(event_id=event_id)
        except ExtPasteEvent.DoesNotExist:
            return Response({"error": "Event not found"}, status=status.HTTP_404_NOT_FOUND)

        feedback, created = ExtAnalystFeedback.objects.update_or_create(
            event=event,
            analyst_id=analyst_id,
            defaults={"verdict": verdict, "comment": comment}
        )

        return Response({
            "status": "success",
            "feedback_id": feedback.id,
            "verdict": feedback.verdict
        }, status=status.HTTP_201_CREATED)

class UserRiskLeaderboardView(APIView):
    def get(self, request):
        # Fetch top riskiest users based on latest behavioral scores
        latest_scores = BehDailyScore.objects.order_by('-date', 'rank_in_day')[:20]
        data = [{
            "user_id": s.user_id,
            "date": str(s.date),
            "probability": s.probability,
            "rank_in_day": s.rank_in_day
        } for s in latest_scores]
        return Response(data, status=status.HTTP_200_OK)