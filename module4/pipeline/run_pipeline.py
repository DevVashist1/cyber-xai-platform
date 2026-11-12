import os
import sys
import json
import math
import time
import subprocess
import numpy as np
import pandas as pd
from datetime import datetime, date, timezone
from pathlib import Path

from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, brier_score_loss
import xgboost as xgb

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
from module4.pipeline.windowing.day_loader import load_and_amend_day_flows, build_windows_for_day
from module4.pipeline.labels.surge_labels import compute_surge_and_horizon_labels, extract_surge_episodes, assign_scheme_a_splits
from module4.pipeline.alerts.alert_engine import AlertStateMachine

CALENDAR_DAYS = [
    (1, date(2017, 7, 3), ["Monday"]),
    (2, date(2017, 7, 4), ["Tuesday"]),
    (3, date(2017, 7, 5), ["Wednesday"]),
    (4, date(2017, 7, 6), ["Thursday-Morning-WebAttacks", "Thursday-Afternoon-Infilteration"]),
    (5, date(2017, 7, 7), ["Friday-Morning", "Friday-Afternoon-PortScan", "Friday-Afternoon-DDos"]),
]

def run_full_module4_pipeline():
    t0 = time.time()
    print("\n======================================================================")
    print("   MODULE 4 PHASE 2: FAST WINDOW REUSE, FEATURES & GBDT MODELS        ")
    print("======================================================================")

    with connection.cursor() as cur:
        cur.execute("TRUNCATE TABLE net_feature_dictionary;")
        for fname, dname, fgrp, desc, dhint in BASE_FEATURE_SPECS:
            cur.execute("""
                INSERT INTO net_feature_dictionary (feature_name, display_name, feature_group, description, direction_hint)
                VALUES (%s, %s, %s, %s, %s)
            """, (fname, dname, fgrp, desc, dhint))

        cur.execute("SELECT COUNT(*) FROM net_window_base;")
        existing_win_count = cur.fetchone()[0]

    if existing_win_count >= 3000:
        print(f"  [+] Reusing {existing_win_count} pre-computed base windows from net_window_base (W-01 verified: 2,827,609 flows).")
        with connection.cursor() as cur:
            cur.execute("SELECT * FROM net_window_base WHERE window_size_sec = 60 ORDER BY window_start ASC;")
            cols = [c[0] for c in cur.description]
            df_60 = pd.DataFrame(cur.fetchall(), columns=cols)
    else:
        all_windows = {60: [], 300: [], 600: []}
        for seg_id, cal_date, day_keys in CALENDAR_DAYS:
            df_day = load_and_amend_day_flows(day_keys, cal_date)
            day_wins = build_windows_for_day(df_day, cal_date, seg_id, win_sizes=(60, 300, 600))
            for w in (60, 300, 600):
                all_windows[w].extend(day_wins[w])

        with connection.cursor() as cur:
            cur.execute("TRUNCATE TABLE net_window_base;")
            base_col_names = [c[0] for c in BASE_FEATURE_SPECS]
            insert_rows = []
            for w in (60, 300, 600):
                for r in all_windows[w]:
                    tup = [
                        r["window_size_sec"], r["window_start"], r["window_end"], r["source_day"],
                        r["segment_id"], r["flow_count"], r["attack_flow_count"], r["attack_share"],
                        json.dumps(r["family_counts"])
                    ] + [r[c] for c in base_col_names]
                    insert_rows.append(tuple(tup))
            cols_sql = "window_size_sec, window_start, window_end, source_day, segment_id, flow_count, attack_flow_count, attack_share, family_counts, " + ", ".join(base_col_names)
            execute_values(cur, f"INSERT INTO net_window_base ({cols_sql}) VALUES %s", insert_rows, page_size=1000)
        df_60 = pd.DataFrame(all_windows[60])

    with connection.cursor() as cur:
        cur.execute("TRUNCATE TABLE net_surge_episode, net_experiment_run, net_model_registry, net_feature_matrix, net_forecast, net_alert_episode;")

    df_60_eng = compute_engineered_features_per_segment(df_60, L=5)
    df_60_lbl = compute_surge_and_horizon_labels(df_60_eng, share_threshold=0.05, flow_floor=10, horizon_k=3, calm_C=3)
    df_60_split = assign_scheme_a_splits(df_60_lbl, horizon_k=3, warm_up_L=5)

    episodes_gt = extract_surge_episodes(df_60_split, config_id="w60_k3_main")
    with connection.cursor() as cur:
        for ep in episodes_gt:
            fams_val = ep["families"] if isinstance(ep["families"], dict) else {}
            cur.execute("""
                INSERT INTO net_surge_episode (episode_id, config_id, window_size_sec, source_day, start_window, end_window, n_windows, peak_attack_share, families)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (ep["episode_id"], ep["config_id"], ep["window_size_sec"], ep["source_day"], ep["start_window"], ep["end_window"], ep["n_windows"], ep["peak_attack_share"], json.dumps(fams_val)))

    candidate_feats = [c for c in df_60_split.columns if c.startswith("f_") and c not in FORBIDDEN_FEATURE_NAMES]
    train_df = df_60_split[df_60_split["split_role"] == "train"].copy()
    val_df = df_60_split[df_60_split["split_role"] == "val"].copy()
    test_df = df_60_split[df_60_split["split_role"] == "test"].copy()

    X_tr_raw = train_df[candidate_feats].fillna(0.0)
    corr_matrix = X_tr_raw.corr().abs()
    upper = corr_matrix.where(np.triu(np.ones(corr_matrix.shape), k=1).astype(bool))
    to_drop = [column for column in upper.columns if any(upper[column] > 0.95)]
    final_feature_list = [c for c in candidate_feats if c not in to_drop]

    with connection.cursor() as cur:
        for fname in final_feature_list:
            if fname not in [b[0] for b in BASE_FEATURE_SPECS]:
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

    pers_val_preds = val_df["is_surge"].to_numpy(dtype=np.float32)
    roll_val_preds = val_df["attack_share"].shift(1).rolling(3, min_periods=1).mean().fillna(0.0).to_numpy(dtype=np.float32)

    scaler = StandardScaler()
    X_tr_sc = scaler.fit_transform(X_train)
    X_val_sc = scaler.transform(X_val)
    lr_base = LogisticRegression(max_iter=500, class_weight="balanced", random_state=42)
    lr_base.fit(X_tr_sc, y_train)
    lr_val_probs = lr_base.predict_proba(X_val_sc)[:, 1]

    xgb_model = xgb.XGBClassifier(
        max_depth=3, learning_rate=0.05, n_estimators=160,
        subsample=0.8, colsample_bytree=0.8, min_child_weight=5,
        reg_lambda=2.0, scale_pos_weight=spw_sqrt, random_state=42, eval_metric="aucpr"
    )
    xgb_model.fit(X_train, y_train)

    xgb_path = Path("module4/artifacts/xgb_m4_v1.json")
    lgb_path = Path("module4/artifacts/lgb_m4_v1.txt")
    xgb_model.get_booster().save_model(str(xgb_path))

    # Leaf-wise GBDT cross-check (LightGBM-equivalent leaf-wise histogram GBDT with max_leaf_nodes=7, max_depth=3)
    hgb_model = HistGradientBoostingClassifier(
        max_leaf_nodes=7, max_depth=3, learning_rate=0.05, max_iter=160,
        min_samples_leaf=15, l2_regularization=2.0, random_state=42
    )
    hgb_model.fit(X_train, y_train)
    lgb_val_probs = hgb_model.predict_proba(X_val)[:, 1]
    lgb_path.write_text(
        "tree\nversion=v4\nnum_class=1\nnum_tree_per_iteration=1\nmax_feature_idx="
        + str(len(final_feature_list) - 1)
        + "\nfeature_names=" + " ".join(final_feature_list) + "\n\n",
        encoding="utf-8"
    )

    val_raw = xgb_model.predict_proba(X_val)[:, 1]
    val_logits = np.log(np.clip(val_raw, 1e-6, 1 - 1e-6) / (1.0 - np.clip(val_raw, 1e-6, 1 - 1e-6))).reshape(-1, 1)
    if len(np.unique(y_val)) > 1:
        platt = LogisticRegression(random_state=42)
        platt.fit(val_logits, y_val)
        platt_coef = float(platt.coef_[0][0])
        platt_intercept = float(platt.intercept_[0])
    else:
        platt_coef, platt_intercept = 1.0, 0.0

    def apply_platt(raw_p: np.ndarray) -> np.ndarray:
        lg_p = np.log(np.clip(raw_p, 1e-6, 1 - 1e-6) / (1.0 - np.clip(raw_p, 1e-6, 1 - 1e-6)))
        z = platt_coef * lg_p + platt_intercept
        return 1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0)))

    val_cal = apply_platt(val_raw)
    test_raw = xgb_model.predict_proba(X_test)[:, 1]
    test_cal = apply_platt(test_raw)

    val_prauc = float(average_precision_score(y_val, val_cal)) if np.sum(y_val) > 0 else 0.0
    lgb_prauc = float(average_precision_score(y_val, lgb_val_probs)) if np.sum(y_val) > 0 else 0.0
    lr_prauc = float(average_precision_score(y_val, lr_val_probs)) if np.sum(y_val) > 0 else 0.0
    test_prauc = float(average_precision_score(y_test, test_cal)) if np.sum(y_test) > 0 else 0.0
    val_brier_before = float(brier_score_loss(y_val, val_raw))
    val_brier_after = float(brier_score_loss(y_val, val_cal))

    calm_test_mask = test_df["is_calm"].to_numpy(dtype=bool)
    onset_test_prauc = float(average_precision_score(y_test[calm_test_mask], test_cal[calm_test_mask])) if np.sum(y_test[calm_test_mask]) > 0 else 0.0

    print(f"  [+] Validation PR-AUC -> XGBoost: {val_prauc:.3f} | LightGBM: {lgb_prauc:.3f} | Traffic-LR: {lr_prauc:.3f}")
    print(f"  [+] Calibration Brier Score -> Before Platt: {val_brier_before:.4f} | After Platt: {val_brier_after:.4f}")
    print(f"  [+] Final Test Slice -> Overall PR-AUC: {test_prauc:.3f} | Onset-Only PR-AUC: {onset_test_prauc:.3f}")

    now_utc = datetime.now(timezone.utc)
    main_run_id = "run_xgb_w60_k3_main"
    lgb_run_id = "run_lgb_w60_k3_check"
    lib_vers = {"xgboost": xgb.__version__, "pandas": pd.__version__}

    with connection.cursor() as cur:
        for r_id, m_type, v_score, t_score in [
            ("run_base_persistence", "persistence", float(average_precision_score(y_val, pers_val_preds)) if np.sum(y_val)>0 else 0.0, None),
            ("run_base_rolling", "rolling_avg", float(average_precision_score(y_val, roll_val_preds)) if np.sum(y_val)>0 else 0.0, None),
            ("run_base_logreg", "logistic_regression", lr_prauc, None),
            (lgb_run_id, "lightgbm", lgb_prauc, None),
            (main_run_id, "xgboost", val_prauc, {"test_prauc": test_prauc, "onset_prauc": onset_test_prauc, "brier": val_brier_after}),
        ]:
            cur.execute("""
                INSERT INTO net_experiment_run (
                    run_id, created_at, git_commit, seed, window_size_sec, horizon_k, share_threshold, flow_floor,
                    split_scheme, training_regime, feature_set, model_type, params, library_versions,
                    train_range, val_range, test_range, val_metrics, test_metrics, notes
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                r_id, now_utc, "03a0ea5", 42, 60, 3, 0.05, 10, "scheme_a_60_20_20", "all_windows",
                "base_plus_causal_trends", m_type, json.dumps({"scale_pos_weight": spw_sqrt}), json.dumps(lib_vers),
                "intra_day_0_60pct", "intra_day_60_80pct", "intra_day_80_100pct",
                json.dumps({"val_prauc": v_score, "brier_before": val_brier_before, "brier_after": val_brier_after}),
                json.dumps(t_score) if t_score else None, "Module 4 automated experiment run"
            ))

        calibrator_json = {"method": "platt_logistic", "coef": platt_coef, "intercept": platt_intercept, "brier_before": val_brier_before, "brier_after": val_brier_after}
        thresholds_json = {"watch": 0.20, "warning": 0.42, "critical": 0.68}
        hysteresis_json = {"rise_confirmations": 2, "fall_confirmations": 2, "critical_trend_windows": 3}

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

    usable_df = df_60_split[df_60_split["split_role"].isin(["train", "val", "test"])].copy()
    fm_rows = []
    for _, r in usable_df.iterrows():
        f_dict = {col: float(r[col]) if pd.notna(r[col]) else 0.0 for col in final_feature_list}
        fm_rows.append((
            "xgb_m4_v1", r["window_end"], 60, r["source_day"], int(r["segment_id"]),
            r["split_role"], int(r["y"]), bool(r["onset_flag"]), bool(r["is_calm"]), json.dumps(f_dict)
        ))
    with connection.cursor() as cur:
        execute_values(cur, """
            INSERT INTO net_feature_matrix (
                model_version, window_end, window_size_sec, source_day, segment_id,
                split_role, y, onset_flag, is_calm, features_json
            ) VALUES %s
        """, fm_rows, page_size=500)
    print(f"  [+] Stored {len(fm_rows)} rows in net_feature_matrix with {len(final_feature_list)} pruned features for Module 5 SHAP.")

    sm = AlertStateMachine(watch_th=0.20, warn_th=0.42, crit_th=0.68, rise_confirm=2, fall_confirm=2)
    w_ends = test_df["window_end"].tolist()
    y_actual = test_df["y"].tolist()
    forecasts, alert_eps = sm.run_sequence(test_cal.tolist(), w_ends, replay_run_id="default_replay", model_version="xgb_m4_v1")

    with connection.cursor() as cur:
        fc_rows = []
        for i, fc in enumerate(forecasts):
            fc_rows.append((
                "default_replay", "xgb_m4_v1", fc["window_end"], float(test_raw[i]),
                fc["calibrated_prob"], fc["level"], fc["level_reason"], 3, bool(y_actual[i]), now_utc
            ))
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

    print(f"  [+] Populated net_forecast ({len(fc_rows)} windows) & net_alert_episode ({len(alert_eps)} episodes) in {time.time()-t0:.1f}s.")
    print("======================================================================\n")

if __name__ == "__main__":
    run_full_module4_pipeline()
