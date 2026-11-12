# Module 4: Network Attack Forecasting (CICIDS2017)

## Architecture & Pipeline
- **Data Source**: Reads `network_flows_clean` (2,827,609 flows across Monday–Friday CICIDS2017), applying 12-hour AM/PM timestamp correction, `end_time` window assignment (`N2`), and zero row dropping (`Section 6`).
- **Windowing & Features (`N3`-`N5`)**: Aggregates 60s, 300s, and 600s windows into `net_window_base` (3,278 windows) with 30 label-free base features and segment-causal lags, rolling z-scores, and 5-window slopes (`110` pruned features stored in `net_feature_matrix` for Module 5 SHAP).
- **Models & Calibration (`N9`-`N12`)**: Trains XGBoost (`xgb_m4_v1.json`) and LightGBM (`lgb_m4_v1.txt`) on identical chronological purged splits (`Scheme A`) and Leave-One-Day-Out folds (`Scheme B`), calibrated via Platt logistic scaling (`Brier: 0.1964 -> 0.1504`).
- **4-Level Alert Engine & Replay (`N14`-`N18`)**: Applies 2-window hysteresis and a 3-window rising-trend gate for `Critical` alerts, populating `net_forecast` and `net_alert_episode` via `/api/v1/network/*`.

## Honest Findings & Limitations (Section 18)
1. **Abrupt Scripted Onsets**: Overall test PR-AUC reaches `0.769`, whereas calm-window `Onset-Only` PR-AUC is `0.013` because CICIDS2017 attacks start abruptly without prolonged pre-attack reconnaissance in the same window granularity.
2. **Network-Wide Scope**: Forecasts network-wide surge probability rather than per-IP risk because attacker/victim IPs in CICIDS2017 are static.
3. **Simulated Live Feed**: `/api/v1/network/replay` steps deterministically through the test timeline (`R-01`, `R-02`) rather than capturing live packets.
