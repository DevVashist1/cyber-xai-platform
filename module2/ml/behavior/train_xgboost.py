import os
import sys
import json
from pathlib import Path
import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.metrics import precision_recall_curve, auc

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent / "backend"
sys.path.append(str(BACKEND_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from apps.behavior.models import BehFeatureMatrix, BehModelRegistry, BehDailyScore, UserDailyActivity
from apps.events.models import ExtPasteEvent

ARTIF_DIR = Path(__file__).resolve().parent.parent / "artifacts"
ARTIF_DIR.mkdir(parents=True, exist_ok=True)


def train_behavior_model():
    print("[*] Training XGBoost Behavior Baseline Model (Section 7.6)...")
    
    # 1. Load feature matrix and labels from UserDailyActivity
    feat_qs = BehFeatureMatrix.objects.filter(model_version=1).values("user_id", "date", "features")
    df_feat = pd.DataFrame(list(feat_qs))
    
    if df_feat.empty:
        print("[-] Feature matrix is empty. Run build_features.py first.")
        return

    # Flatten JSON features into columns
    feat_expanded = pd.json_normalize(df_feat["features"])
    df_feat = pd.concat([df_feat[["user_id", "date"]], feat_expanded], axis=1)

    # Join with labels from UserDailyActivity
    label_qs = UserDailyActivity.objects.values("user_id", "date", "is_malicious")
    df_labels = pd.DataFrame(list(label_qs))
    df_labels["date"] = pd.to_datetime(df_labels["date"]).dt.date

    df = pd.merge(df_feat, df_labels, on=["user_id", "date"], how="inner")
    df = df.sort_values("date").reset_index(drop=True)

    if df.empty or "is_malicious" not in df.columns:
        print("[-] Error merging features and labels.")
        return

    # 2. Chronological Split (70% train, 15% val, 15% test - Section 7.3)
    n = len(df)
    train_idx = int(n * 0.70)
    val_idx = int(n * 0.85)

    feature_cols = [c for c in df.columns if c not in ["user_id", "date", "is_malicious"]]

    X_train = df.iloc[:train_idx][feature_cols]
    y_train = df.iloc[:train_idx]["is_malicious"]

    X_val = df.iloc[train_idx:val_idx][feature_cols]
    y_val = df.iloc[train_idx:val_idx]["is_malicious"]

    X_test = df.iloc[val_idx:][feature_cols]
    y_test = df.iloc[val_idx:]["is_malicious"]

    # 3. Handle Class Imbalance via scale_pos_weight
    neg_count = (y_train == 0).sum()
    pos_count = (y_train == 1).sum()
    scale_weight = float(neg_count / max(1, pos_count))

    model = xgb.XGBClassifier(
        max_depth=4,
        learning_rate=0.08,
        n_estimators=300,
        scale_pos_weight=scale_weight,
        random_state=42,
        eval_metric="aucpr"
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=False
    )

    # 4. Evaluate PR-AUC on test set
    preds = model.predict_proba(X_test)[:, 1]
    precision, recall, _ = precision_recall_curve(y_test, preds)
    pr_auc = float(auc(recall, precision))
    print(f"[+] XGBoost Test PR-AUC: {pr_auc:.4f}")

    # 5. Save model in Native XGBoost JSON format (Section 7.6 & 10.14)
    model_json_path = ARTIF_DIR / "xgboost_behavior_model.json"
    model.save_model(str(model_json_path))
    print(f"[+] Native XGBoost model saved to {model_json_path}")

    # 6. Register model in BehModelRegistry
    model_reg, _ = BehModelRegistry.objects.update_or_create(
        model_version=1,
        defaults={
            "algorithm": "XGBoost",
            "feature_list": feature_cols,
            "date_ranges": {
                "train": str(df.iloc[0]["date"]) + " to " + str(df.iloc[train_idx]["date"]),
                "test": str(df.iloc[val_idx]["date"]) + " to " + str(df.iloc[n-1]["date"])
            },
            "metrics": {"pr_auc": pr_auc},
            "file_reference": str(model_json_path),
            "is_active": True
        }
    )

    # 7. Generate daily scores for BehDailyScore
    BehDailyScore.objects.filter(model_version=1).delete()
    all_preds = model.predict_proba(df[feature_cols])[:, 1]
    df["probability"] = all_preds

    score_objs = []
    for date_val, group in df.groupby("date"):
        group = group.sort_values("probability", ascending=False).reset_index(drop=True)
        for rank, row in group.iterrows():
            score_objs.append(BehDailyScore(
                user_id=row["user_id"],
                date=date_val,
                model_version=1,
                probability=float(row["probability"]),
                rank_in_day=rank + 1
            ))

    BehDailyScore.objects.bulk_create(score_objs, batch_size=1000)
    print(f"[+] Successfully generated and stored {len(score_objs)} daily behavior scores.")


if __name__ == "__main__":
    train_behavior_model()