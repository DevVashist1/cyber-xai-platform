# Module 3 Threat Model & Tamper Resistance Limits
- **Session 0 vs User Session**: Runs in the interactive user session to observe clipboard sequence numbers and foreground window process names.
- **Tamper Detection**: Uses a local lock marker (`running.lock`) and 60s server heartbeats. Forced termination triggers `ungraceful_stop` or `heartbeat_gap` alerts and raises Rule `AG-09` (`[T1562.001]`) if preceded by USB or high-risk clipboard activity.
- **Clock Tampering**: Server compares `occurred_at` against server UTC receipt time and raises a `clock_skew` alert if drift exceeds 300 seconds.
