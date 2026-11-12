import json
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from django.db import connection
from module4.pipeline.replay.replay_service import run_deterministic_replay


class StaffRequiredMixin:
    """Section 5.2: All /api/v1/network/* endpoints require staff login."""
    permission_classes = [IsAdminUser]


class NetworkForecastView(StaffRequiredMixin, APIView):
    def get(self, request):
        replay_run_id = request.query_params.get("replay_run_id", "default_replay")
        ts_from = request.query_params.get("from")
        ts_to = request.query_params.get("to")
        limit = min(int(request.query_params.get("limit", 500)), 2000)
        offset = int(request.query_params.get("offset", 0))

        conds = ["replay_run_id = %s"]
        params = [replay_run_id]
        if ts_from:
            conds.append("window_end >= %s")
            params.append(ts_from)
        if ts_to:
            conds.append("window_end <= %s")
            params.append(ts_to)

        where_sql = " AND ".join(conds)
        with connection.cursor() as cur:
            cur.execute(f"""
                SELECT replay_run_id, model_version, window_end, raw_score, calibrated_prob,
                       level, level_reason, horizon_k, actual_surge_in_horizon
                FROM net_forecast
                WHERE {where_sql}
                ORDER BY window_end ASC
                LIMIT %s OFFSET %s
            """, params + [limit, offset])
            rows = cur.fetchall()

        results = [
            {
                "replay_run_id": r[0],
                "model_version": r[1],
                "window_end": r[2].isoformat() if hasattr(r[2], "isoformat") else str(r[2]),
                "raw_score": round(float(r[3]), 4),
                "calibrated_prob": round(float(r[4]), 4),
                "level": int(r[5]),
                "level_reason": r[6],
                "horizon_k": int(r[7]),
                "actual_surge_in_horizon": r[8]
            }
            for r in rows
        ]
        return Response({"count": len(results), "results": results}, status=status.HTTP_200_OK)


class NetworkAlertsView(StaffRequiredMixin, APIView):
    def get(self, request):
        replay_run_id = request.query_params.get("replay_run_id", "default_replay")
        min_level = int(request.query_params.get("min_level", 2))
        with connection.cursor() as cur:
            cur.execute("""
                SELECT episode_id, replay_run_id, model_version, max_level,
                       start_window, end_window, peak_prob, status, matched_surge_episode_id
                FROM net_alert_episode
                WHERE replay_run_id = %s AND max_level >= %s
                ORDER BY start_window ASC
            """, (replay_run_id, min_level))
            rows = cur.fetchall()

        alerts = [
            {
                "episode_id": r[0],
                "replay_run_id": r[1],
                "model_version": r[2],
                "max_level": int(r[3]),
                "start_window": r[4].isoformat() if hasattr(r[4], "isoformat") else str(r[4]),
                "end_window": r[5].isoformat() if hasattr(r[5], "isoformat") else str(r[5]),
                "peak_prob": round(float(r[6]), 4),
                "status": r[7],
                "matched_surge_episode_id": r[8]
            }
            for r in rows
        ]
        return Response({"count": len(alerts), "results": alerts}, status=status.HTTP_200_OK)


class NetworkActiveModelView(StaffRequiredMixin, APIView):
    def get(self, request):
        with connection.cursor() as cur:
            cur.execute("""
                SELECT model_version, run_id, model_type, file_ref, feature_list,
                       window_size_sec, horizon_k, calibrator, thresholds, hysteresis, is_active, created_at
                FROM net_model_registry
                WHERE is_active = TRUE
                ORDER BY created_at DESC LIMIT 1
            """)
            r = cur.fetchone()
        if not r:
            return Response({"error": "No active model"}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            "model_version": r[0],
            "run_id": r[1],
            "model_type": r[2],
            "file_ref": r[3],
            "feature_count": len(r[4]) if isinstance(r[4], list) else len(json.loads(r[4])),
            "window_size_sec": r[5],
            "horizon_k": r[6],
            "calibrator": r[7] if isinstance(r[7], dict) else json.loads(r[7]),
            "thresholds": r[8] if isinstance(r[8], dict) else json.loads(r[8]),
            "hysteresis": r[9] if isinstance(r[9], dict) else json.loads(r[9]),
            "is_active": r[10],
            "created_at": r[11].isoformat() if hasattr(r[11], "isoformat") else str(r[11])
        }, status=status.HTTP_200_OK)


class NetworkReplayControlView(StaffRequiredMixin, APIView):
    def post(self, request):
        replay_run_id = request.data.get("replay_run_id", "live_sim_replay")
        speed = float(request.data.get("speed_multiplier", 60.0))
        model_version = request.data.get("model_version")
        res = run_deterministic_replay(replay_run_id=replay_run_id, model_version=model_version, speed_multiplier=speed)
        return Response(res, status=status.HTTP_200_OK)
