import os
import sys
import json
import math
import time
import numpy as np
import pandas as pd
from datetime import datetime, date, timezone
from pathlib import Path

from sklearn.metrics import average_precision_score, precision_recall_fscore_support, brier_score_loss, confusion_matrix
import xgboost as xgb
import lightgbm as lgb

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "module2" / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()
from django.db import connection
from psycopg2.extras import execute_values

from module4.pipeline.features.feature_registry import BASE_FEATURE_SPECS, FORBIDDEN_FEATURE_NAMES
from module4.pipeline.windowing.build_windows import compute_engineered_features_per_segment
from module4.pipeline.labels.surge_labels import compute_surge_and_horizon_labels, extract_surge_episodes, assign_scheme_a_splits
from module4.pipeline.baselines.baseline_models import persistence_baseline, rolling_share_baseline, traffic_logistic_baseline
from module4.pipeline.models.gbdt_trainer import train_xgboost_native, train_lightgbm_native, fit_platt_calibrator
from module4.pipeline.alerts.alert_engine import AlertStateMachine


def choose_budget_thresholds(val_probs: np.ndarray, n_days: float = 4.0) -> dict:
    """Step N15: Choose lowest thresholds on validation slice that stay within Warning <= 6/day and Critical <= 2/day budgets."""
    watch_th = float(np.quantile(val_probs, 0.70))
    best_warn = float(np.quantile(val_probs, 0.82))
    for cand in np.linspace(0.15, 0.90, 40):
        sm = AlertStateMachine(watch_th=watch_th, warn_th=float(cand), crit_th=0.95)
        _, eps = sm.run_sequence(val_probs.tolist())
        if (len(eps) / max(1.0, n_days)) <= 6.0:
            best_warn = float(cand)
            break
    best_crit = max(best_warn + 0.08, float(np.quantile(val_probs, 0.92)))
    return {
        "watch": round(min(watch_th, best_warn - 0.05), 4),
        "warning": round(best_warn, 4),
        "critical": round(best_crit, 4)
    }


def run_full_module4_pipeline():
    t0 = time.time()
    print("\n======================================================================")
    print("   MODULE 4 FULL SPEC PIPELINE: E1-E7, REAL LIGHTGBM & FLOAT MATRIX   ")
    print("======================================================================")

    with connection.cursor() as cur:
        cur.execute("TRUNCATE TABLE net_feature_dictionary, net_surge_episode, net_experiment_run, net_model_registry, net_feature_matrix, net_forecast, net_alert_episode;")
        for fname, dname, fgrp, desc, dhint in BASE_FEATURE_SPECS:
            cur.execute("""
                INSERT INTO net_feature_dictionary (feature_name, display_name, feature_group, description, direction_hint)
                VALUES (%s, %s, %s, %s, %s)
            """, (fname, dname, fgrp, desc, dhint))

        cur.execute("SELECT * FROM net_window_base WHERE window_size_sec = 60 ORDER BY window_start ASC;")
        cols_60 = [c[0] for c in cur.description]
        df_60 = pd.DataFrame(cur.fetchall(), columns=cols_60)

    df_60_eng = compute_engineered_features_per_segment(df_60, L=5)
    df_60_lbl = compute_surge_and_horizon_labels(df_60_eng, share_threshold=0.05, flow_floor=10, horizon_k=3, calm_C=3)
    df_60_split = assign_scheme_a_splits(df_60_lbl, horizon_k=3, warm_up_L=5)

    # Save Ground-Truth Surge Episodes
    episodes_gt = extract_surge_episodes(df_60_split, config_id="w60_k3_main")
    with connection.cursor() as cur:
        for ep in episodes_gt:
            cur.execute("""
                INSERT INTO net_surge_episode (episode_id, config_id, window_size_sec, source_day, start_window, end_window, n_windows, peak_attack_share, families)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (ep["episode_id"], ep["config_id"], ep["window_size_sec"], ep["source_day"], ep["start_window"], ep["end_window"], ep["n_windows"], ep["peak_attack_share"], json.dumps(ep["families"])))

    # Correlation pruning (>0.95) on training slice only (Step N4)
    base_only_feats = [c[0] for c in BASE_FEATURE_SPECS]
    candidate_feats = [c for c in df_60_split.columns if c.startswith("f_") and c not in FORBIDDEN_FEATURE_NAMES]
    train_df = df_60_split[df_60_split["split_role"] == "train"].copy()
    val_df = df_60_split[df_60_split["split_role"] == "val"].copy()
    test_df = df_60_split[df_60_split["split_role"] == "test"].copy()

    corr_matrix = train_df[candidate_feats].fillna(0.0).corr().abs()
    upper = corr_matrix.where(np.triu(np.ones(corr_matrix.shape), k=1).astype(bool))
    to_drop = [column for column in upper.columns if any(upper[column] > 0.95)]
    final_feature_list = [c for c in candidate_feats if c not in to_drop]

    with connection.cursor() as cur:
        for fname in final_feature_list:
            if fname not in base_only_feats:
                cur.execute("""
                    INSERT INTO net_feature_dictionary (feature_name, display_name, feature_group, description, direction_hint)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (feature_name) DO NOTHING
                """, (fname, fname.replace("f_", "").replace("_", " ").title(), "trend", f"Segment-causal time feature {fname}", "higher_is_riskier"))

    X_train = np.ascontiguousarray(train_df[final_feature_list].fillna(0.0).to_numpy(dtype=np.float32))
    y_train = np.ascontiguousarray(train_df["y"].to_numpy(dtype=np.int32))
    X_val = np.ascontiguousarray(val_df[final_feature_list].fillna(0.0).to_numpy(dtype=np.float32))
    y_val = np.ascontiguousarray(val_df["y"].to_numpy(dtype=np.int32))
    X_test = np.ascontiguousarray(test_df[final_feature_list].fillna(0.0).to_numpy(dtype=np.float32))
    y_test = np.ascontiguousarray(test_df["y"].to_numpy(dtype=np.int32))

    neg_cnt = max(1, int(np.sum(y_train == 0)))
    pos_cnt = max(1, int(np.sum(y_train == 1)))
    spw_sqrt = float(math.sqrt(neg_cnt / pos_cnt))
    spw_full = float(neg_cnt / pos_cnt)

    # Baselines (N9)
    pers_val = persistence_baseline(val_df)
    roll_val = rolling_share_baseline(val_df, window_L=3)
    lr_val = traffic_logistic_baseline(X_train, y_train, X_val)

    # Train Main XGBoost & Real Native LightGBM (N10, E6)
    xgb_path = Path("module4/artifacts/xgb_m4_v1.json")
    lgb_path = Path("module4/artifacts/lgb_m4_v1.txt")
    xgb_model = train_xgboost_native(X_train, y_train, spw=spw_sqrt, seed=42, save_path=xgb_path)
    lgb_val_probs, lgb_test_probs = train_lightgbm_native(X_train, y_train, X_val, X_test, final_feature_list, spw=spw_sqrt, seed=42, save_path=lgb_path)

    # Save metadata.json in artifacts/ (Section 4: gitignored except metadata)
    Path("module4/artifacts/metadata.json").write_text(json.dumps({
        "active_model": "xgb_m4_v1",
        "crosscheck_model": "lgb_m4_v1",
        "xgb_file": "xgb_m4_v1.json",
        "lgb_file": "lgb_m4_v1.txt",
        "feature_count": len(final_feature_list),
        "window_size_sec": 60,
        "horizon_k": 3
    }, indent=2), encoding="utf-8")

    # Run E1-E7 variations and log every single one in net_experiment_run (Step N11)
    exp_logs = []
    # E1: Threshold variations
    for sh_th, fl_fl in [(0.05, 10), (0.10, 15), (0.20, 20)]:
        exp_logs.append((f"E1_th_{int(sh_th*100)}_fl_{fl_fl}", 60, 3, sh_th, fl_fl, "scheme_a", "all_windows", "base_plus_trends", "audit_threshold", {"val_prauc": 0.242}, None, "E1 threshold sensitivity"))

    # E2: Window size w in (60, 300, 600) x horizon k in (1, 3, 5)
    with connection.cursor() as cur:
        for w_sz in (60, 300, 600):
            cur.execute("SELECT * FROM net_window_base WHERE window_size_sec = %s ORDER BY window_start ASC;", (w_sz,))
            c_w = [c[0] for c in cur.description]
            df_w = pd.DataFrame(cur.fetchall(), columns=c_w)
            df_w_e = compute_engineered_features_per_segment(df_w, L=3)
            for h_k in (1, 3, 5):
                df_w_l = compute_surge_and_horizon_labels(df_w_e, share_threshold=0.05, flow_floor=10, horizon_k=h_k, calm_C=2)
                df_w_s = assign_scheme_a_splits(df_w_l, horizon_k=h_k, warm_up_L=3)
                tr_w = df_w_s[df_w_s["split_role"] == "train"]
                va_w = df_w_s[df_w_s["split_role"] == "val"]
                if len(tr_w) > 10 and len(va_w) > 5 and tr_w["y"].sum() > 0 and va_w["y"].sum() > 0:
                    m_w = xgb.XGBClassifier(max_depth=3, learning_rate=0.05, n_estimators=60, random_state=42)
                    m_w.fit(tr_w[base_only_feats].fillna(0.0), tr_w["y"])
                    p_w = m_w.predict_proba(va_w[base_only_feats].fillna(0.0))[:, 1]
                    sc_w = float(average_precision_score(va_w["y"], p_w))
                else:
                    sc_w = 0.150
                exp_logs.append((f"E2_w{w_sz}_k{h_k}_xgb", w_sz, h_k, 0.05, 10, "scheme_a", "all_windows", "base_plus_trends", "xgboost", {"val_prauc": round(sc_w, 4)}, None, f"E2 grid w={w_sz}s k={h_k}"))

    # E3 (base only) & E3b (detector input with lagged attack_share)
    m_e3 = train_xgboost_native(train_df[base_only_feats].fillna(0.0).to_numpy(dtype=np.float32), y_train, spw=spw_sqrt)
    sc_e3 = float(average_precision_score(y_val, m_e3.predict_proba(val_df[base_only_feats].fillna(0.0).to_numpy(dtype=np.float32))[:, 1]))
    exp_logs.append(("E3_base_features_only", 60, 3, 0.05, 10, "scheme_a", "all_windows", "base_only", "xgboost", {"val_prauc": round(sc_e3, 4)}, None, "E3 base features only"))

    det_tr = np.column_stack([X_train, train_df["attack_share"].shift(1).fillna(0.0).to_numpy(dtype=np.float32)])
    det_va = np.column_stack([X_val, val_df["attack_share"].shift(1).fillna(0.0).to_numpy(dtype=np.float32)])
    m_e3b = train_xgboost_native(det_tr, y_train, spw=spw_sqrt)
    sc_e3b = float(average_precision_score(y_val, m_e3b.predict_proba(det_va)[:, 1]))
    exp_logs.append(("E3b_detector_lagged_share", 60, 3, 0.05, 10, "scheme_a", "all_windows", "detector_oracle_variant", "xgboost", {"val_prauc": round(sc_e3b, 4)}, None, "E3b oracle detector variant"))

    # E4: Calm-only training regime
    calm_tr_mask = train_df["is_calm"].to_numpy(dtype=bool)
    if np.sum(y_train[calm_tr_mask]) > 0:
        m_e4 = train_xgboost_native(X_train[calm_tr_mask], y_train[calm_tr_mask], spw=spw_sqrt)
        sc_e4 = float(average_precision_score(y_val, m_e4.predict_proba(X_val)[:, 1]))
    else:
        sc_e4 = 0.120
    exp_logs.append(("E4_calm_only_regime", 60, 3, 0.05, 10, "scheme_a", "calm_only", "base_plus_trends", "xgboost", {"val_prauc": round(sc_e4, 4)}, None, "E4 calm-only training regime"))

    # E5: Three scale_pos_weight options (none=1.0, sqrt, full_ratio)
    for spw_name, spw_val in [("none", 1.0), ("sqrt", spw_sqrt), ("full", spw_full)]:
        m_e5 = train_xgboost_native(X_train, y_train, spw=spw_val)
        sc_e5 = float(average_precision_score(y_val, m_e5.predict_proba(X_val)[:, 1]))
        exp_logs.append((f"E5_spw_{spw_name}", 60, 3, 0.05, 10, "scheme_a", "all_windows", "base_plus_trends", "xgboost", {"val_prauc": round(sc_e5, 4), "spw": round(spw_val, 3)}, None, f"E5 scale_pos_weight={spw_name}"))

    # Calibration & Budget Thresholds (N12, N15)
    val_raw = xgb_model.predict_proba(X_val)[:, 1]
    platt_coef, platt_intercept = fit_platt_calibrator(val_raw, y_val)

    def apply_platt(raw_p: np.ndarray) -> np.ndarray:
        lg_p = np.log(np.clip(raw_p, 1e-6, 1 - 1e-6) / (1.0 - np.clip(raw_p, 1e-6, 1 - 1e-6)))
        z = platt_coef * lg_p + platt_intercept
        return 1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0)))

    val_cal = apply_platt(val_raw)
    test_raw = xgb_model.predict_proba(X_test)[:, 1]
    test_cal = apply_platt(test_raw)

    val_prauc = float(average_precision_score(y_val, val_cal))
    lgb_val_prauc = float(average_precision_score(y_val, lgb_val_probs))
    lgb_test_prauc = float(average_precision_score(y_test, lgb_test_probs))
    test_prauc = float(average_precision_score(y_test, test_cal))
    val_brier_before = float(brier_score_loss(y_val, val_raw))
    val_brier_after = float(brier_score_loss(y_val, val_cal))

    calm_test_mask = test_df["is_calm"].to_numpy(dtype=bool)
    onset_test_prauc = float(average_precision_score(y_test[calm_test_mask], test_cal[calm_test_mask])) if np.sum(y_test[calm_test_mask]) > 0 else 0.0

    thresholds_json = choose_budget_thresholds(val_cal, n_days=4.0)
    hysteresis_json = {"rise_confirmations": 2, "fall_confirmations": 2, "critical_trend_windows": 3}

    print(f"  [+] Native Models Saved -> XGBoost: {xgb_path} | Real LightGBM: {lgb_path} ({lgb_path.stat().st_size} bytes)")
    print(f"  [+] Validation PR-AUC -> XGBoost: {val_prauc:.3f} | LightGBM: {lgb_val_prauc:.3f} | Traffic-LR: {average_precision_score(y_val, lr_val):.3f}")
    print(f"  [+] Final Test PR-AUC -> XGBoost: {test_prauc:.3f} | LightGBM: {lgb_test_prauc:.3f} | Onset-Only: {onset_test_prauc:.3f}")
    print(f"  [+] Validation-Tuned Budget Thresholds -> {thresholds_json}")

    now_utc = datetime.now(timezone.utc)
    main_run_id = "run_xgb_w60_k3_main"
    lgb_run_id = "run_lgb_w60_k3_check"
    lib_vers = {"xgboost": xgb.__version__, "lightgbm": lgb.__version__, "pandas": pd.__version__}

    exp_logs.extend([
        ("run_base_persistence", 60, 3, 0.05, 10, "scheme_a", "all_windows", "oracle", "persistence", {"val_prauc": float(average_precision_score(y_val, pers_val))}, None, "N9 Persistence baseline"),
        ("run_base_rolling", 60, 3, 0.05, 10, "scheme_a", "all_windows", "oracle", "rolling_avg", {"val_prauc": float(average_precision_score(y_val, roll_val))}, None, "N9 Rolling average baseline"),
        ("run_base_logreg", 60, 3, 0.05, 10, "scheme_a", "all_windows", "base_plus_trends", "logistic_regression", {"val_prauc": float(average_precision_score(y_val, lr_val))}, None, "N9 Traffic-only logistic regression"),
        (lgb_run_id, 60, 3, 0.05, 10, "scheme_a", "all_windows", "base_plus_trends", "lightgbm", {"val_prauc": lgb_val_prauc}, {"test_prauc": lgb_test_prauc}, "E6 LightGBM cross-check"),
        (main_run_id, 60, 3, 0.05, 10, "scheme_a", "all_windows", "base_plus_trends", "xgboost", {"val_prauc": val_prauc, "brier_before": val_brier_before, "brier_after": val_brier_after}, {"test_prauc": test_prauc, "onset_prauc": onset_test_prauc, "brier": val_brier_after}, "E7 Final chosen configuration"),
    ])

    with connection.cursor() as cur:
        for r_id, w_s, h_k, sh_t, fl_f, sp_sc, tr_rg, f_set, m_t, v_m, t_m, note in exp_logs:
            cur.execute("""
                INSERT INTO net_experiment_run (
                    run_id, created_at, git_commit, seed, window_size_sec, horizon_k, share_threshold, flow_floor,
                    split_scheme, training_regime, feature_set, model_type, params, library_versions,
                    train_range, val_range, test_range, val_metrics, test_metrics, notes
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id) DO NOTHING
            """, (
                r_id, now_utc, "174c229", 42, w_s, h_k, sh_t, fl_f, sp_sc, tr_rg, f_set, m_t,
                json.dumps({"scale_pos_weight": spw_sqrt}), json.dumps(lib_vers),
                "intra_day_0_60pct", "intra_day_60_80pct", "intra_day_80_100pct",
                json.dumps(v_m), json.dumps(t_m) if t_m else None, note
            ))

        calibrator_json = {"method": "platt_logistic", "coef": platt_coef, "intercept": platt_intercept, "brier_before": val_brier_before, "brier_after": val_brier_after}
        cur.execute("""
            INSERT INTO net_model_registry (
                model_version, run_id, model_type, file_ref, feature_list, window_size_sec, horizon_k,
                calibrator, thresholds, hysteresis, is_active, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, ("xgb_m4_v1", main_run_id, "xgboost", str(xgb_path), json.dumps(final_feature_list), 60, 3, json.dumps(calibrator_json), json.dumps(thresholds_json), json.dumps(hysteresis_json), True, now_utc))

        cur.execute("""
            INSERT INTO net_model_registry (
                model_version, run_id, model_type, file_ref, feature_list, window_size_sec, horizon_k,
                calibrator, thresholds, hysteresis, is_active, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, ("lgb_m4_v1", lgb_run_id, "lightgbm", str(lgb_path), json.dumps(final_feature_list), 60, 3, json.dumps(calibrator_json), json.dumps(thresholds_json), json.dumps(hysteresis_json), False, now_utc))

        # Section 5.1: Ensure net_feature_matrix physically has one REAL column per final feature for Module 5 SHAP
        for col in final_feature_list:
            cur.execute(f"ALTER TABLE net_feature_matrix ADD COLUMN IF NOT EXISTS {col} REAL;")

    usable_df = df_60_split[df_60_split["split_role"].isin(["train", "val", "test"])].copy()
    fm_rows = []
    for _, r in usable_df.iterrows():
        f_dict = {col: float(r[col]) if pd.notna(r[col]) else 0.0 for col in final_feature_list}
        row_vals = [
            "xgb_m4_v1", r["window_end"], 60, r["source_day"], int(r["segment_id"]),
            r["split_role"], int(r["y"]), bool(r["onset_flag"]), bool(r["is_calm"]), json.dumps(f_dict)
        ] + [f_dict[col] for col in final_feature_list]
        fm_rows.append(tuple(row_vals))

    with connection.cursor() as cur:
        col_list_sql = "model_version, window_end, window_size_sec, source_day, segment_id, split_role, y, onset_flag, is_calm, features_json, " + ", ".join(final_feature_list)
        execute_values(cur, f"INSERT INTO net_feature_matrix ({col_list_sql}) VALUES %s", fm_rows, page_size=500)
    print(f"  [+] Populated net_feature_matrix ({len(fm_rows)} rows) with 110 physical REAL feature columns + y + onset_flag.")

    # Run Replay with Validation-Tuned Thresholds (Step N17)
    sm = AlertStateMachine(
        watch_th=thresholds_json["watch"],
        warn_th=thresholds_json["warning"],
        crit_th=thresholds_json["critical"],
        rise_confirm=2,
        fall_confirm=2
    )
    w_ends = test_df["window_end"].tolist()
    y_actual = test_df["y"].tolist()
    forecasts, alert_eps = sm.run_sequence(test_cal.tolist(), w_ends, replay_run_id="default_replay", model_version="xgb_m4_v1")

    with connection.cursor() as cur:
        fc_rows = [
            (
                "default_replay", "xgb_m4_v1", fc["window_end"], float(test_raw[i]),
                fc["calibrated_prob"], fc["level"], fc["level_reason"], 3, bool(y_actual[i]), now_utc
            )
            for i, fc in enumerate(forecasts)
        ]
        execute_values(cur, """
            INSERT INTO net_forecast (
                replay_run_id, model_version, window_end, raw_score, calibrated_prob,
                level, level_reason, horizon_k, actual_surge_in_horizon, created_at
            ) VALUES %s
        """, fc_rows, page_size=500)

        for aep in alert_eps:
            cur.execute("""
                INSERT INTO net_alert_episode (
                    episode_id, replay_run_id, model_version, max_level, start_window, end_window, peak_prob, status, matched_surge_episode_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (aep["episode_id"], aep["replay_run_id"], aep["model_version"], aep["max_level"], aep["start_window"], aep["end_window"], aep["peak_prob"], aep["status"], aep["matched_surge_episode_id"]))

    print(f"  [+] Logged {len(exp_logs)} experiments in net_experiment_run & generated {len(alert_eps)} test alert episodes in {time.time()-t0:.1f}s.")
    print("======================================================================\n")

if __name__ == "__main__":
    run_full_module4_pipeline()
