import json
import numpy as np
import xgboost as xgb
from datetime import datetime, timezone
from django.db import connection
from psycopg2.extras import execute_values
from module4.pipeline.alerts.alert_engine import AlertStateMachine


def run_deterministic_replay(replay_run_id: str = "api_replay_1", model_version: str = None, speed_multiplier: float = 60.0) -> dict:
    """Step N17 & Tests R-01, R-02: Step through the test timeline window by window, score, calibrate, apply hysteresis, and write net_forecast & net_alert_episode."""
    with connection.cursor() as cur:
        if model_version:
            cur.execute("""
                SELECT model_version, file_ref, feature_list, window_size_sec, horizon_k, calibrator, thresholds, hysteresis
                FROM net_model_registry WHERE model_version = %s LIMIT 1
            """, (model_version,))
        else:
            cur.execute("""
                SELECT model_version, file_ref, feature_list, window_size_sec, horizon_k, calibrator, thresholds, hysteresis
                FROM net_model_registry WHERE is_active = TRUE ORDER BY created_at DESC LIMIT 1
            """)
        reg = cur.fetchone()
        if not reg:
            raise RuntimeError("No active model found in net_model_registry.")

        m_ver, file_ref, feat_list, win_sec, h_k, cal_cfg, th_cfg, hyst_cfg = reg
        if isinstance(feat_list, str): feat_list = json.loads(feat_list)
        if isinstance(cal_cfg, str): cal_cfg = json.loads(cal_cfg)
        if isinstance(th_cfg, str): th_cfg = json.loads(th_cfg)
        if isinstance(hyst_cfg, str): hyst_cfg = json.loads(hyst_cfg)

        # Load time-ordered test slice rows from net_feature_matrix
        cur.execute("""
            SELECT window_end, y, features_json
            FROM net_feature_matrix
            WHERE model_version = %s AND split_role = 'test'
            ORDER BY window_end ASC
        """, (m_ver,))
        rows = cur.fetchall()

    if not rows:
        return {"replay_run_id": replay_run_id, "windows_scored": 0, "alert_episodes": 0}

    booster = xgb.Booster()
    booster.load_model(file_ref)

    w_ends = []
    y_true = []
    X_list = []
    for w_end, y_val, f_json in rows:
        f_dict = json.loads(f_json) if isinstance(f_json, str) else f_json
        w_ends.append(w_end)
        y_true.append(bool(y_val))
        X_list.append([float(f_dict.get(c, 0.0)) for c in feat_list])

    X_mat = np.array(X_list, dtype=np.float32)
    dmat = xgb.DMatrix(X_mat)
    raw_probs = booster.predict(dmat)

    # Apply stored Platt scaling calibrator
    coef = float(cal_cfg.get("coef", 1.0))
    intercept = float(cal_cfg.get("intercept", 0.0))
    logits = np.log(np.clip(raw_probs, 1e-6, 1.0 - 1e-6) / (1.0 - np.clip(raw_probs, 1e-6, 1.0 - 1e-6)))
    cal_probs = 1.0 / (1.0 + np.exp(-np.clip(coef * logits + intercept, -30.0, 30.0)))

    sm = AlertStateMachine(
        watch_th=float(th_cfg.get("watch", 0.20)),
        warn_th=float(th_cfg.get("warning", 0.42)),
        crit_th=float(th_cfg.get("critical", 0.68)),
        rise_confirm=int(hyst_cfg.get("rise_confirmations", 2)),
        fall_confirm=int(hyst_cfg.get("fall_confirmations", 2))
    )
    forecasts, alert_eps = sm.run_sequence(cal_probs.tolist(), w_ends, replay_run_id=replay_run_id, model_version=m_ver)

    now_utc = datetime.now(timezone.utc)
    with connection.cursor() as cur:
        cur.execute("DELETE FROM net_forecast WHERE replay_run_id = %s AND model_version = %s", (replay_run_id, m_ver))
        cur.execute("DELETE FROM net_alert_episode WHERE replay_run_id = %s AND model_version = %s", (replay_run_id, m_ver))

        fc_tuples = [
            (
                replay_run_id, m_ver, fc["window_end"], float(raw_probs[i]),
                float(fc["calibrated_prob"]), int(fc["level"]), fc["level_reason"],
                int(h_k), y_true[i], now_utc
            )
            for i, fc in enumerate(forecasts)
        ]
        execute_values(cur, """
            INSERT INTO net_forecast (
                replay_run_id, model_version, window_end, raw_score, calibrated_prob,
                level, level_reason, horizon_k, actual_surge_in_horizon, created_at
            ) VALUES %s
        """, fc_tuples, page_size=500)

        for aep in alert_eps:
            cur.execute("""
                INSERT INTO net_alert_episode (
                    episode_id, replay_run_id, model_version, max_level, start_window, end_window, peak_prob, status, matched_surge_episode_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                aep["episode_id"], replay_run_id, m_ver, aep["max_level"],
                aep["start_window"], aep["end_window"], aep["peak_prob"],
                aep["status"], aep["matched_surge_episode_id"]
            ))

    return {
        "replay_run_id": replay_run_id,
        "model_version": m_ver,
        "windows_scored": len(fc_tuples),
        "alert_episodes": len(alert_eps),
        "speed_multiplier": speed_multiplier
    }
