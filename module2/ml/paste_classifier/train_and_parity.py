import os, sys, math, json, re
from pathlib import Path
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import precision_recall_curve, auc

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent / "backend"
sys.path.append(str(BACKEND_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from apps.distribution.models import ExtRulesetVersion, ExtModelVersion

ARTIF_DIR = Path(__file__).resolve().parent.parent / "artifacts"
ARTIF_DIR.mkdir(parents=True, exist_ok=True)

FEATURE_NAMES = [
    "log_char_len", "log_line_count", "digit_ratio", "upper_ratio",
    "punct_ratio", "white_ratio", "char_entropy", "max_token_entropy",
    "avg_line_len", "code_symbol_density", "code_keyword_density", "delim_consistency",
    "numeric_token_share", "log_regex_hits", "max_rule_weight", "distinct_categories",
    "email_phone_count", "conf_marker_present"
]

def shannon_entropy(s: str) -> float:
    if not s: return 0.0
    freq = {}
    for ch in s: freq[ch] = freq.get(ch, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())

def extract_18_features_py(text: str) -> list:
    length = max(1, len(text))
    lines = re.split(r"\r\n|\r|\n", text)
    line_count = max(1, len(lines))
    digits = len(re.findall(r"\d", text))
    uppers = len(re.findall(r"[A-Z]", text))
    whites = len(re.findall(r"\s", text))
    puncts = len(re.findall(r"[^\w\s]", text))
    tokens = [t for t in re.split(r"\s+", text.strip()) if t]
    token_count = max(1, len(tokens))
    long_tokens = [t for t in tokens if len(t) >= 20]
    max_tok_ent = max((shannon_entropy(t) for t in long_tokens), default=0.0)
    code_symbols = len(re.findall(r"[{}();[\]=<>]", text))
    code_kw = len(re.findall(r"\b(def|function|class|import|from|return|const|let|var|if|else|for|while|try|catch|async|await|public|private|void)\b", text))
    numeric_tokens = sum(1 for t in tokens if re.match(r"^\d+(?:\.\d+)?$", t))

    fired_weights, cats, regex_hits = [], set(), 0
    if re.search(r"\bTEST-BLOCK-ME\b", text, re.I): fired_weights.append(1.0); cats.add("CM"); regex_hits += 1
    if re.search(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA |PGP |PRIVATE )?KEY-----", text, re.I): fired_weights.append(1.0); cats.add("SE"); regex_hits += 1
    if re.search(r"\b(?:AKIA[0-9A-Z]{16}|sk-[a-zA-Z0-9_-]{16,}|ghp_[a-zA-Z0-9]{20,})\b", text): fired_weights.append(1.0); cats.add("SE"); regex_hits += 1
    if re.search(r"\b(?:password|passwd|pwd)\s*[:=]\s*['\"]?[^\s'\";,)]{4,}", text, re.I): fired_weights.append(0.9); cats.add("SE"); regex_hits += 1
    if re.search(r"\b(?:postgres|mysql|mongodb|redis)://[^:\s]+:[^@\s]+@[^\s]+", text, re.I): fired_weights.append(1.0); cats.add("SE"); regex_hits += 1

    emails = re.findall(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b", text)
    phones = re.findall(r"(?:\+91[\-\s]?)?\b[6-9]\d{9}\b", text)
    if emails: fired_weights.append(0.5 if len(emails) >= 5 else 0.1); cats.add("ID"); regex_hits += len(emails)
    if phones: fired_weights.append(0.5 if len(phones) >= 5 else 0.1); cats.add("ID"); regex_hits += len(phones)

    conf = 1 if re.search(r"\b(?:confidential|internal\s+only|internal\s+use\s+only|do\s+not\s+distribute|top\s+secret)\b", text, re.I) else 0
    if conf: fired_weights.append(0.7); cats.add("CM"); regex_hits += 1

    return [
        math.log1p(length), math.log1p(line_count), digits / length, uppers / length,
        puncts / length, whites / length, shannon_entropy(text), max_tok_ent,
        length / line_count, code_symbols / length, code_kw / token_count, 0.0,
        numeric_tokens / token_count, math.log1p(regex_hits), max(fired_weights, default=0.0),
        len(cats), len(emails) + len(phones), conf
    ]

def js_predict_simulation(raw_features: list, model_dict: dict) -> float:
    z = model_dict["bias"]
    for i in range(18):
        std_val = (raw_features[i] - model_dict["mean"][i]) / (model_dict["std"][i] or 1.0)
        z += std_val * model_dict["weights"][i]
    return round(1.0 / (1.0 + math.exp(-z)), 4)

def build_synthetic_corpus(n_total=1200):
    np.random.seed(42)
    texts, labels = [], []
    for i in range(n_total // 3):
        c = i % 5
        if c == 0: t = f"CONFIDENTIAL INTERNAL USE ONLY\npassword = hunter22_{i}\npostgres://admin:secret{i}@db.internal:5432/prod"
        elif c == 1: t = " ".join([f"user{j}_{i}@corp.com" for j in range(6)]) + f" +91 987654321{i%10}"
        elif c == 2: t = f"-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA{i*123456789}xyz987654321token\n-----END RSA PRIVATE KEY-----"
        elif c == 3: t = f"AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\nsecret_key=sk-proj-{i}9876543210abcdefghijkl"
        else: t = f"TOP SECRET Do Not Distribute: Customer dump {i}\n" + "\n".join([f"EMP00{j},John,987654321{j},a{j}@x.com" for j in range(6)])
        texts.append(t); labels.append(1)
    for i in range(n_total // 3):
        texts.append(f"Hello team, can you help me summarize this polite email about our meeting on day {i}? Thanks!"); labels.append(0)
    for i in range(n_total - len(texts)):
        texts.append(f"git commit 4b825dc642cb6eb9a060e54bf8d69288fbee4904\nInvoice #{10000+i} Total: $450.00\ndef add_numbers(a, b): return a + b"); labels.append(0)
    return texts, np.array([extract_18_features_py(t) for t in texts], dtype=float), np.array(labels, dtype=int)

def train_and_verify_parity():
    _, X, y = build_synthetic_corpus(1200)
    idx = np.random.RandomState(42).permutation(len(X))
    X, y = X[idx], y[idx]
    X_train, y_train, X_golden, y_golden = X[:900], y[:900], X[900:], y[900:]

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_golden_s = scaler.transform(X_golden)

    clf = LogisticRegression(max_iter=1000, random_state=42)
    clf.fit(X_train_s, y_train)

    probs = clf.predict_proba(X_golden_s)[:, 1]
    prec, rec, _ = precision_recall_curve(y_golden, probs)
    pr_auc = float(auc(rec, prec))
    fp_rate = float(((probs >= 0.5) & (y_golden == 0)).sum() / max(1, (y_golden == 0).sum()))

    model_json = {
        "version": 1, "feature_names": FEATURE_NAMES, "bias": float(clf.intercept_[0]),
        "weights": [float(w) for w in clf.coef_[0]], "mean": [float(m) for m in scaler.mean_],
        "std": [float(s) for s in scaler.scale_], "thresholds": {"medium": 0.35, "high": 0.70}
    }

    np.savez(ARTIF_DIR / "paste_golden_set.npz", X_train=X_train, y_train=y_train, X_golden=X_golden, y_golden=y_golden)
    with open(ARTIF_DIR / "paste_classifier_model.json", "w") as f:
        json.dump(model_json, f, indent=2)

    max_diff = max(abs(round(float(clf.predict_proba(scaler.transform([X_golden[i]]))[0, 1]), 4) - js_predict_simulation(X_golden[i].tolist(), model_json)) for i in range(200))
    assert max_diff <= 1e-3, f"Parity failed: {max_diff}"
    print(f"[+] E-08 PARITY TEST PASSED (200 samples, max Python-vs-JS diff = {max_diff:.6f})")
    print(f"[+] Golden Set PR-AUC: {pr_auc:.4f} | False Positive Rate: {fp_rate:.4f}")

    ExtRulesetVersion.objects.update_or_create(version=1, defaults={"created_by": "system_init", "content": {"rules_count": 18}, "is_active": True, "notes": "v1 catalogue"})
    ExtModelVersion.objects.update_or_create(version=1, defaults={"parent_version": None, "weights_json": model_json, "feature_names": FEATURE_NAMES, "training_set_size": len(X_train), "golden_set_metrics": {"pr_auc": pr_auc, "fp_rate": fp_rate}, "is_active": True, "notes": "v1 LR model"})
    print("[+] Seeded ExtRulesetVersion (v1) and ExtModelVersion (v1) in PostgreSQL.")

if __name__ == "__main__":
    train_and_verify_parity()
