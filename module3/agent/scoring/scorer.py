import math
import regex as re

VERHOEFF_D = [
    [0,1,2,3,4,5,6,7,8,9],[1,2,3,4,0,6,7,8,9,5],[2,3,4,0,1,7,8,9,5,6],[3,4,0,1,2,8,9,5,6,7],[4,0,1,2,3,9,5,6,7,8],
    [5,9,8,7,6,0,4,3,2,1],[6,5,9,8,7,1,0,4,3,2],[7,6,5,9,8,2,1,0,4,3],[8,7,6,5,9,3,2,1,0,4],[9,8,7,6,5,4,3,2,1,0]
]
VERHOEFF_P = [
    [0,1,2,3,4,5,6,7,8,9],[1,5,7,6,2,8,3,0,9,4],[5,8,0,3,7,9,6,1,4,2],[8,9,1,6,0,4,3,5,2,7],
    [9,4,5,3,1,2,6,8,7,0],[4,2,8,6,5,7,3,9,0,1],[2,7,9,3,8,0,6,4,1,5],[7,0,4,6,9,1,3,2,5,8]
]

DEFAULT_LR_MODEL = {
    "bias": -2.45,
    "weights": [0.15, 0.12, 0.30, 0.10, 0.18, -0.10, 0.35, 0.45, 0.10, 0.10, 0.10, 0.35, 0.25, 0.65, 0.95, 0.50, 0.45, 0.70],
    "mean": [4.5, 1.5, 0.05, 0.08, 0.05, 0.15, 3.8, 3.2, 45.0, 0.02, 0.01, 0.1, 0.05, 0.2, 0.1, 0.2, 0.2, 0.02],
    "std":  [1.8, 1.2, 0.10, 0.08, 0.06, 0.08, 0.8, 1.2, 35.0, 0.04, 0.03, 0.3, 0.12, 0.6, 0.3, 0.6, 1.0, 0.15]
}

def is_valid_luhn(num_str: str) -> bool:
    digits = "".join(ch for ch in num_str if ch.isdigit())
    if len(digits) < 13 or len(digits) > 19 or len(set(digits)) == 1:
        return False
    total = 0
    double = False
    for ch in reversed(digits):
        d = int(ch)
        if double:
            d *= 2
            if d > 9: d -= 9
        total += d
        double = not double
    return total % 10 == 0

def is_valid_verhoeff(num_str: str) -> bool:
    digits = "".join(ch for ch in num_str if ch.isdigit())
    if len(digits) != 12 or digits[0] in ("0", "1"):
        return False
    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = VERHOEFF_D[c][VERHOEFF_P[i % 8][int(ch)]]
    return c == 0

def compute_shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    freq = {}
    for ch in s:
        freq[ch] = freq.get(ch, 0) + 1
    n = len(s)
    return -sum((cnt / n) * math.log2(cnt / n) for cnt in freq.values())

def score_clipboard_text(raw_text: str, max_bytes: int = 102400, regex_timeout: float = 0.25) -> dict:
    truncated = False
    if len(raw_text) > max_bytes:
        raw_text = raw_text[:max_bytes]
        truncated = True

    try:
        fired = []
        total_hits = 0

        if re.search(r"\bTEST-BLOCK-ME\b", raw_text, re.I, timeout=regex_timeout):
            fired.append({"id": "CM-01", "cat": "TEST_BLOCK_TRIGGER", "w": 1.0, "hard": True})
            total_hits += 1

        id01 = [m for m in re.findall(r"\b[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}\b", raw_text, timeout=regex_timeout) if is_valid_verhoeff(m)]
        if id01:
            fired.append({"id": "ID-01", "cat": "NATIONAL_ID_VERHOEFF", "w": 0.8, "hard": False})
            total_hits += len(id01)

        pan = re.findall(r"\b[A-Z]{3}[ABCFGHLJPTF][A-Z]\d{4}[A-Z]\b", raw_text, timeout=regex_timeout)
        if pan:
            fired.append({"id": "ID-02", "cat": "PAN_IDENTIFIER", "w": 0.7, "hard": False})
            total_hits += len(pan)

        ssn = re.findall(r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b", raw_text, timeout=regex_timeout)
        if ssn:
            fired.append({"id": "ID-03", "cat": "US_SSN", "w": 0.8, "hard": False})
            total_hits += len(ssn)

        cards = [m for m in re.findall(r"\b(?:\d[ -]*?){13,19}\b", raw_text, timeout=regex_timeout) if is_valid_luhn(m)]
        if cards:
            fired.append({"id": "ID-04", "cat": "PAYMENT_CARD_LUHN", "w": 0.9, "hard": True})
            total_hits += len(cards)

        emails = re.findall(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b", raw_text, timeout=regex_timeout)
        if emails:
            wt = min(0.75, 0.5 + (len(emails) - 5) * 0.05) if len(emails) >= 5 else 0.1
            fired.append({"id": "ID-05", "cat": "EMAIL_PII", "w": wt, "hard": False})
            total_hits += len(emails)

        phones = re.findall(r"(?:\+91[\-\s]?)?\b[6-9]\d{9}\b", raw_text, timeout=regex_timeout)
        if phones:
            wt = 0.5 if len(phones) >= 5 else 0.1
            fired.append({"id": "ID-06", "cat": "PHONE_NUMBER", "w": wt, "hard": False})
            total_hits += len(phones)

        if re.search(r"\b[A-Z]{4}0[A-Z0-9]{6}\b", raw_text, timeout=regex_timeout) and re.search(r"\b(account|acct|bank|ifsc)\b", raw_text, re.I, timeout=regex_timeout):
            fired.append({"id": "ID-07", "cat": "BANK_IFSC_ACCOUNT", "w": 0.6, "hard": False})
            total_hits += 1

        if re.search(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA |PGP |PRIVATE )?KEY-----", raw_text, re.I, timeout=regex_timeout):
            fired.append({"id": "SE-01", "cat": "PRIVATE_KEY", "w": 1.0, "hard": True})
            total_hits += 1

        if re.search(r"\b(?:AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|sk-[a-zA-Z0-9_-]{16,}|gh[pousr]_[a-zA-Z0-9]{20,}|AIza[0-9A-Za-z\-_]{35})\b", raw_text, timeout=regex_timeout):
            fired.append({"id": "SE-02", "cat": "CLOUD_API_KEY", "w": 1.0, "hard": True})
            total_hits += 1

        se03 = re.search(r"\b(?:key|token|secret|api_key|apikey|auth)\s*[:=]\s*[\"']?([A-Za-z0-9_\-+/=]{16,})[\"']?", raw_text, re.I, timeout=regex_timeout)
        if se03:
            cand = se03.group(1)
            is_uuid = bool(re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", cand, re.I))
            is_git = bool(re.match(r"^[0-9a-f]{40}$", cand, re.I))
            if not is_uuid and not is_git and compute_shannon_entropy(cand) >= 3.6:
                fired.append({"id": "SE-03", "cat": "HIGH_ENTROPY_SECRET", "w": 0.8, "hard": False})
                total_hits += 1

        if re.search(r"\b(?:password|passwd|pwd)\s*[:=]\s*[\"']?(?!None\b|null\b|undefined\b|true\b|false\b|models\.|forms\.|char\b)[^\s\"';,)]{4,}", raw_text, re.I, timeout=regex_timeout):
            fired.append({"id": "SE-04", "cat": "PASSWORD_ASSIGNMENT", "w": 0.9, "hard": True})
            total_hits += 1

        if re.search(r"\b(?:postgres|postgresql|mysql|mongodb(?:\+srv)?|redis|amqp|mssql):\/\/[^:\s]+:[^@\s]+@[^\s]+", raw_text, re.I, timeout=regex_timeout):
            fired.append({"id": "SE-05", "cat": "DB_CONNECTION_STRING", "w": 1.0, "hard": True})
            total_hits += 1

        if re.search(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}\b", raw_text, timeout=regex_timeout):
            fired.append({"id": "SE-06", "cat": "JWT_TOKEN", "w": 0.8, "hard": False})
            total_hits += 1

        if re.search(r"\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9_\-\.~+/]+=*", raw_text, re.I, timeout=regex_timeout):
            fired.append({"id": "SE-07", "cat": "BEARER_TOKEN", "w": 0.7, "hard": False})
            total_hits += 1

        lines = re.split(r"\r\n|\r|\n", raw_text)
        code_kw = len(re.findall(r"\b(def|function|class|import|from|return|const|let|var|if|else|for|while|try|catch|async|await|public|private|void)\b", raw_text, timeout=regex_timeout))
        if len(lines) >= 30 and code_kw >= 8:
            fired.append({"id": "CO-01", "cat": "LARGE_CODE_BLOCK", "w": 0.25, "hard": False})
            total_hits += 1

        if re.search(r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}|[\w-]+\.(?:internal|corp|lan|intranet))\b", raw_text, re.I, timeout=regex_timeout):
            fired.append({"id": "CO-02", "cat": "INTERNAL_INFRA_IP_HOST", "w": 0.5, "hard": False})
            total_hits += 1

        if re.search(r"\b(?:git@|https?:\/\/(?:gitlab|github|bitbucket)\.internal)\b", raw_text, re.I, timeout=regex_timeout):
            fired.append({"id": "CO-03", "cat": "INTERNAL_REPO_PATH", "w": 0.5, "hard": False})
            total_hits += 1

        if re.search(r"\b(?:SELECT\s+\*\s+FROM|INSERT\s+INTO|DELETE\s+FROM|DROP\s+TABLE)\b[\s\S]{1,80}\b(?:user_daily_activity|ext_paste_event|ext_device|beh_daily_score|users)\b", raw_text, re.I, timeout=regex_timeout):
            fired.append({"id": "CO-04", "cat": "INTERNAL_SQL_QUERY", "w": 0.5, "hard": False})
            total_hits += 1

        has_conf = bool(re.search(r"\b(?:confidential|internal\s+only|internal\s+use\s+only|do\s+not\s+distribute|not\s+for\s+external|top\s+secret)\b", raw_text, re.I, timeout=regex_timeout))
        if has_conf:
            fired.append({"id": "CM-01", "cat": "CONFIDENTIALITY_MARKER", "w": 0.7, "hard": False})
            total_hits += 1

        if re.search(r"\b(?:PROJECT[-_\s]?OMEGA|PROJECT[-_\s]?TITAN|OPERATION[-_\s]?NIGHTFALL)\b", raw_text, re.I, timeout=regex_timeout):
            fired.append({"id": "CM-02", "cat": "PROJECT_CODENAME", "w": 0.6, "hard": False})
            total_hits += 1

        cert_ids = set(re.findall(r"\b[A-Z]{3}\d{4}\b", raw_text, timeout=regex_timeout))
        if len(cert_ids) >= 3:
            fired.append({"id": "CM-03", "cat": "BULK_EMPLOYEE_IDS", "w": 0.5, "hard": False})
            total_hits += len(cert_ids)

        prod_comp = 1.0
        max_w = 0.0
        hard_fired = False
        for r in fired:
            prod_comp *= (1.0 - r["w"])
            if r["w"] > max_w: max_w = r["w"]
            if r["hard"]: hard_fired = True
        regex_score = round(1.0 - prod_comp, 4)

        length = max(1, len(raw_text))
        line_count = max(1, len(lines))
        digits = sum(1 for c in raw_text if c.isdigit())
        uppers = sum(1 for c in raw_text if c.isupper())
        whites = sum(1 for c in raw_text if c.isspace())
        puncts = len(re.findall(r"[^\w\s]", raw_text, timeout=regex_timeout))
        tokens = [t for t in raw_text.strip().split() if t]
        tok_cnt = max(1, len(tokens))
        long_toks = [t for t in tokens if len(t) >= 20]
        max_tok_ent = max((compute_shannon_entropy(t) for t in long_toks), default=0.0)
        code_syms = sum(1 for c in raw_text if c in "{}();[]=<>")
        num_toks = sum(1 for t in tokens if re.match(r"^\d+(?:\.\d+)?$", t))
        distinct_cats = len(set(r["id"].split("-")[0] for r in fired))

        feats = [
            math.log1p(length), math.log1p(line_count), digits / length, uppers / length,
            puncts / length, whites / length, compute_shannon_entropy(raw_text), max_tok_ent,
            length / line_count, code_syms / length, code_kw / tok_cnt, 0.0,
            num_toks / tok_cnt, math.log1p(total_hits), max_w,
            distinct_cats, len(emails) + len(phones), 1 if has_conf else 0
        ]

        z = DEFAULT_LR_MODEL["bias"]
        for i in range(18):
            std_val = (feats[i] - DEFAULT_LR_MODEL["mean"][i]) / (DEFAULT_LR_MODEL["std"][i] or 1.0)
            z += std_val * DEFAULT_LR_MODEL["weights"][i]
        ml_score = round(1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z)))), 4)

        final_score = 0.6 * regex_score + 0.4 * ml_score
        if hard_fired and final_score < 0.90:
            final_score = 0.90
        final_score = round(min(1.0, final_score), 4)

        risk_tier = "high" if final_score >= 0.70 else ("medium" if final_score >= 0.35 else "low")
        return {
            "char_count": len(raw_text),
            "line_count": line_count,
            "regex_score": round(regex_score, 3),
            "ml_score": round(ml_score, 3),
            "final_score": round(final_score, 3),
            "risk_tier": risk_tier,
            "matched_categories": [f"{r['id']}:{r['cat']}" for r in fired],
            "truncated": truncated,
            "timed_out": False
        }
    except TimeoutError:
        return {
            "char_count": len(raw_text),
            "line_count": raw_text.count("\n") + 1,
            "regex_score": 0.5,
            "ml_score": 0.5,
            "final_score": 0.5,
            "risk_tier": "medium",
            "matched_categories": ["TIMEOUT:UNSCORED_PATHOLOGICAL"],
            "truncated": truncated,
            "timed_out": True
        }
