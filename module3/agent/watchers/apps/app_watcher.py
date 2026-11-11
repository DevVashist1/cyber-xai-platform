import time
import uuid
from datetime import datetime, timezone

DEFAULT_AI_APPS = {
    "chatgpt.exe": "ChatGPT_Desktop",
    "claude.exe": "Claude_Desktop",
    "cursor.exe": "Cursor_AI",
    "copilot.exe": "Copilot_App",
    "ollama.exe": "Ollama"
}
BROWSER_PROCS = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe"}
AI_KEYWORDS = ["chatgpt", "claude", "gemini", "copilot", "perplexity", "deepseek", "huggingchat"]


class AiDesktopAppWatcher:
    """Section 10 (Steps P1 to P3): Track foreground focus blocks for AI desktop apps & unmonitored browser AI tabs."""
    def __init__(self, outbox, ai_app_map: dict = None):
        self.outbox = outbox
        self.ai_app_map = ai_app_map or DEFAULT_AI_APPS
        self.active_label = None
        self.started_at_iso = None
        self.focus_seconds = 0

    def match_foreground(self, process_name: str, window_title: str = "") -> str:
        proc_low = (process_name or "").lower()
        if proc_low in self.ai_app_map:
            return self.ai_app_map[proc_low]
        # Step P3: Tag browser windows whose title matches AI keywords
        if proc_low in BROWSER_PROCS and window_title:
            t_low = window_title.lower()
            for kw in AI_KEYWORDS:
                if kw in t_low:
                    return f"{proc_low}:{kw}"
        return None

    def record_poll_tick(self, process_name: str, window_title: str = "", elapsed_seconds: int = 5, now_iso: str = None):
        now_iso = now_iso or datetime.now(timezone.utc).isoformat()
        matched_label = self.match_foreground(process_name, window_title)

        if matched_label:
            if self.active_label == matched_label:
                self.focus_seconds += elapsed_seconds
            else:
                ev = self.flush_active_session(ended_at_iso=now_iso)
                self.active_label = matched_label
                self.started_at_iso = now_iso
                self.focus_seconds = elapsed_seconds
                return ev
        else:
            if self.active_label is not None:
                return self.flush_active_session(ended_at_iso=now_iso)
        return None

    def flush_active_session(self, ended_at_iso: str = None):
        if not self.active_label or self.focus_seconds <= 0:
            self.active_label = None
            self.focus_seconds = 0
            return None
        end_iso = ended_at_iso or datetime.now(timezone.utc).isoformat()
        ev = {
            "event_id": str(uuid.uuid4()),
            "event_type": "app_session",
            "occurred_at": end_iso,
            "app_label": self.active_label[:40],
            "started_at": self.started_at_iso or end_iso,
            "ended_at": end_iso,
            "focus_seconds": int(self.focus_seconds),
            "risk_tier": "low"
        }
        self.outbox.enqueue(ev)
        self.active_label = None
        self.started_at_iso = None
        self.focus_seconds = 0
        return ev
