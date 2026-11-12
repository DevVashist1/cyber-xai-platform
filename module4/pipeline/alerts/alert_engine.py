import uuid

class AlertStateMachine:
    def __init__(self, watch_th: float = 0.25, warn_th: float = 0.50, crit_th: float = 0.75,
                 rise_confirm: int = 2, fall_confirm: int = 2):
        self.watch_th = watch_th
        self.warn_th = warn_th
        self.crit_th = crit_th
        self.rise_confirm = rise_confirm
        self.fall_confirm = fall_confirm
        self.reset()

    def reset(self):
        self.current_level = 0
        self.up_streak = 0
        self.down_streak = 0
        self.prob_history = []

    def _raw_candidate_level(self, p: float) -> tuple:
        self.prob_history.append(float(p))
        if p >= self.crit_th:
            if len(self.prob_history) >= 3:
                p_t2, p_t1, p_t = self.prob_history[-3], self.prob_history[-2], self.prob_history[-1]
                if (p_t >= p_t1 >= p_t2) and (p_t > p_t2 + 1e-6):
                    return 3, "above Critical threshold with 3-window rising trend"
            return 2, "above Critical threshold but flat/non-rising trend (capped at Warning)"
        elif p >= self.warn_th:
            return 2, "above Warning threshold"
        elif p >= self.watch_th:
            return 1, "above Watch threshold"
        return 0, "below Watch threshold"

    def step(self, prob: float) -> tuple:
        cand_level, cand_reason = self._raw_candidate_level(prob)
        if cand_level > self.current_level:
            self.up_streak += 1
            self.down_streak = 0
            if self.up_streak >= self.rise_confirm:
                self.current_level = cand_level
                self.up_streak = 0
                return self.current_level, f"{cand_reason} for {self.rise_confirm} consecutive windows"
            return self.current_level, f"holding level {self.current_level} (awaiting rise confirmation {self.up_streak}/{self.rise_confirm})"
        elif cand_level < self.current_level:
            self.down_streak += 1
            self.up_streak = 0
            if self.down_streak >= self.fall_confirm:
                self.current_level = cand_level
                self.down_streak = 0
                return self.current_level, f"de-escalated to level {self.current_level} after {self.fall_confirm} windows below threshold"
            return self.current_level, f"holding level {self.current_level} (cooldown {self.down_streak}/{self.fall_confirm})"
        else:
            self.up_streak = 0
            self.down_streak = 0
            return self.current_level, f"steady at level {self.current_level} ({cand_reason})"

    def run_sequence(self, probs: list, window_ends: list = None, replay_run_id: str = "batch", model_version: str = "v1") -> tuple:
        self.reset()
        forecasts = []
        episodes = []
        active_ep = None

        for i, p in enumerate(probs):
            lvl, reason = self.step(p)
            w_end = window_ends[i] if window_ends is not None else i
            forecasts.append({"window_end": w_end, "calibrated_prob": float(p), "level": int(lvl), "level_reason": reason})

            if lvl >= 2:
                if active_ep is None:
                    active_ep = {
                        "episode_id": str(uuid.uuid4()),
                        "replay_run_id": replay_run_id,
                        "model_version": model_version,
                        "max_level": int(lvl),
                        "start_window": w_end,
                        "end_window": w_end,
                        "peak_prob": float(p),
                        "status": "open",
                        "matched_surge_episode_id": None
                    }
                else:
                    active_ep["end_window"] = w_end
                    if lvl > active_ep["max_level"]:
                        active_ep["max_level"] = int(lvl)
                    if p > active_ep["peak_prob"]:
                        active_ep["peak_prob"] = float(p)
            else:
                if active_ep is not None:
                    active_ep["status"] = "closed"
                    episodes.append(active_ep)
                    active_ep = None

        if active_ep is not None:
            active_ep["status"] = "closed"
            episodes.append(active_ep)
        return forecasts, episodes
