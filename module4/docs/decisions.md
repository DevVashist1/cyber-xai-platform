# Module 4 Design Decisions & Threshold Audit (`decisions.md`)

1. **Flow-to-Window Assignment (`N2`)**: Every flow is assigned by `end_time = timestamp + max(0, flow_duration_us / 1e6)` so slow-attack durations never leak future knowledge (`W-03`).
2. **Module 1 Amendments (`Section 6`)**: Preserved all rare classes (including `Heartbleed` and `Infiltration`), replaced `Inf/NaN` rates with `NULL` (`0 rows dropped`), and verified monotonic 24-hour timestamps per capture day.
3. **Surge Label Thresholds (`N6`, `E1`)**: Selected `share_threshold = 0.20` (20% attack share) and scaled flow floors (`15` at 1m, `60` at 5m, `110` at 10m), ensuring every split in Scheme A (60/20/20) and Scheme B (Leave-One-Day-Out) contains both ongoing surge windows and calm pre-surge onset events (`S-04`).
4. **Hysteresis & Critical Trend (`N14`-`N16`)**: `rise_confirmations = 2`, `fall_confirmations = 2`, and `Critical` requires `prob >= critical_threshold` plus a rising 3-window trend (`p_t >= p_{t-1} >= p_{t-2}` and `p_t > p_{t-2}`).
