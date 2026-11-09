import os, sys
from pathlib import Path
import numpy as np
from sklearn.metrics import precision_recall_curve, auc

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent / "backend"
sys.path.append(str(BACKEND_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from apps.distribution.models import ExtModelVersion
ARTIF_DIR = Path(__file__).resolve().parent.parent / "artifacts"

def evaluate_candidate_on_golden(weights, bias, mean, std, X_golden, y_golden):
    X_std = (X_golden - mean) / np.where(std == 0, 1.0, std)
    z = X_std @ np.array(weights) + bias
    probs = 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))
    prec, rec, _ = precision_recall_curve(y_golden, probs)
    return {"pr_auc": float(auc(rec, prec)), "fp_rate": float(((probs >= 0.5) & (y_golden == 0)).sum() / max(1, (y_golden == 0).sum()))}

def run_retraining_loop(simulate_bad_model=False):
    active = ExtModelVersion.objects.filter(is_active=True).order_by("-version").first()
    data = np.load(ARTIF_DIR / "paste_golden_set.npz")
    X_golden, y_golden = data["X_golden"], data["y_golden"]
    act_m = active.golden_set_metrics

    weights = [-w for w in active.weights_json["weights"]] if simulate_bad_model else active.weights_json["weights"]
    cand_m = evaluate_candidate_on_golden(weights, active.weights_json["bias"], np.array(active.weights_json["mean"]), np.array(active.weights_json["std"]), X_golden, y_golden)

    if cand_m["pr_auc"] < act_m["pr_auc"] - 1e-4 or cand_m["fp_rate"] > act_m["fp_rate"] + 1e-4:
        print(f"[!] RETRAINING GUARD REJECTED CANDIDATE MODEL: PR-AUC={cand_m['pr_auc']:.4f} vs Active={act_m['pr_auc']:.4f}")
        return {"status": "rejected", "candidate_metrics": cand_m}
    return {"status": "published", "candidate_metrics": cand_m}
