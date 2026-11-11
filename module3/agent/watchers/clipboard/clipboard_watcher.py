import uuid
from datetime import datetime, timezone
from module3.agent.scoring.scorer import score_clipboard_text

PASSWORD_MANAGER_FORMATS = {
    "ExcludeClipboardContentFromMonitorProcessing",
    "CanIncludeInClipboardHistory",
    "ClipboardViewerIgnore"
}

AI_DESKTOP_PROCESSES = {"chatgpt.exe", "claude.exe", "cursor.exe", "copilot.exe", "ollama.exe"}
BROWSER_PROCESSES = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe"}
IDE_PROCESSES = {"code.exe", "pycharm64.exe", "devenv.exe"}
OFFICE_PROCESSES = {"winword.exe", "excel.exe", "powerpoint.exe", "outlook.exe"}
AI_KEYWORDS = ["chatgpt", "claude", "gemini", "copilot", "perplexity", "deepseek", "huggingchat"]


class ClipboardAndAppWatcher:
    def __init__(self, outbox):
        self.outbox = outbox
        self.low_risk_clipboard_count = 0
        self.last_seq_num = None

    @staticmethod
    def classify_foreground(process_name: str, window_title: str = "") -> dict:
        proc_low = (process_name or "unknown").lower()
        title_low = (window_title or "").lower()

        if proc_low in AI_DESKTOP_PROCESSES:
            fg_class = "ai_desktop_app"
        elif proc_low in BROWSER_PROCESSES:
            fg_class = "browser"
        elif proc_low in IDE_PROCESSES:
            fg_class = "ide"
        elif proc_low in OFFICE_PROCESSES:
            fg_class = "office"
        else:
            fg_class = "other"

        matched_kw = None
        for kw in AI_KEYWORDS:
            if kw in title_low:
                matched_kw = kw
                break

        ai_ctx = (fg_class == "ai_desktop_app") or (matched_kw is not None)
        return {
            "foreground_app": process_name or "unknown",
            "foreground_class": fg_class,
            "ai_context": ai_ctx,
            "ai_keyword": matched_kw
        }

    def process_clipboard_change(self, content_kind: str = "text", text_data: str = "",
                                 file_list_count: int = 0, active_formats: set = None,
                                 foreground_app: str = "notepad.exe", window_title: str = "",
                                 occurred_at: str = None):
        if active_formats and PASSWORD_MANAGER_FORMATS.intersection(active_formats):
            return {"status": "skipped_password_manager"}

        ctx = self.classify_foreground(foreground_app, window_title)
        occ = occurred_at or datetime.now(timezone.utc).isoformat()

        if content_kind == "text":
            sc = score_clipboard_text(text_data or "")
            if sc["risk_tier"] == "low" and not ctx["ai_context"]:
                self.low_risk_clipboard_count += 1
                return {"status": "counted_low_risk", "low_risk_count": self.low_risk_clipboard_count, "score": sc}

            ev = {
                "event_id": str(uuid.uuid4()),
                "event_type": "clipboard",
                "occurred_at": occ,
                "content_kind": "text",
                "char_count": sc["char_count"],
                "line_count": sc["line_count"],
                "file_count": None,
                "matched_categories": sc["matched_categories"],
                "regex_score": sc["regex_score"],
                "ml_score": sc["ml_score"],
                "final_score": sc["final_score"],
                "risk_tier": sc["risk_tier"],
                "foreground_app": ctx["foreground_app"],
                "foreground_class": ctx["foreground_class"],
                "ai_context": ctx["ai_context"],
                "ai_keyword": ctx["ai_keyword"],
                "ruleset_version": 1,
                "model_version": 1
            }
            self.outbox.enqueue(ev)
            return {"status": "stored", "event": ev}

        elif content_kind == "files":
            ev = {
                "event_id": str(uuid.uuid4()),
                "event_type": "clipboard",
                "occurred_at": occ,
                "content_kind": "files",
                "char_count": None,
                "line_count": None,
                "file_count": int(file_list_count),
                "matched_categories": [],
                "regex_score": 0.4,
                "ml_score": 0.4,
                "final_score": 0.4,
                "risk_tier": "medium" if file_list_count >= 5 or ctx["ai_context"] else "low",
                "foreground_app": ctx["foreground_app"],
                "foreground_class": ctx["foreground_class"],
                "ai_context": ctx["ai_context"],
                "ai_keyword": ctx["ai_keyword"],
                "ruleset_version": 1,
                "model_version": 1
            }
            if ev["risk_tier"] in ("medium", "high") or ctx["ai_context"]:
                self.outbox.enqueue(ev)
                return {"status": "stored", "event": ev}
            self.low_risk_clipboard_count += 1
            return {"status": "counted_low_risk"}

        else:
            if ctx["ai_context"]:
                ev = {
                    "event_id": str(uuid.uuid4()),
                    "event_type": "clipboard",
                    "occurred_at": occ,
                    "content_kind": content_kind[:8],
                    "char_count": None, "line_count": None, "file_count": None,
                    "matched_categories": [], "regex_score": 0.1, "ml_score": 0.1, "final_score": 0.1,
                    "risk_tier": "low",
                    "foreground_app": ctx["foreground_app"],
                    "foreground_class": ctx["foreground_class"],
                    "ai_context": True,
                    "ai_keyword": ctx["ai_keyword"],
                    "ruleset_version": 1, "model_version": 1
                }
                self.outbox.enqueue(ev)
                return {"status": "stored", "event": ev}
            self.low_risk_clipboard_count += 1
            return {"status": "counted_low_risk"}
