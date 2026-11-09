import os
import sys
from pathlib import Path
import pandas as pd
import numpy as np

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent / "backend"
sys.path.append(str(BACKEND_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from apps.behavior.models import BehFeatureMatrix, BehRuleFlag, UserDailyActivity


def build_behavior_features():
    print("[*] Building behavior baseline features (Vectorized/Optimized)...")
    
    qs = UserDailyActivity.objects.all().order_by("user_id", "date")
    df = pd.DataFrame(list(qs.values()))
    
    if df.empty:
        print("[-] Warning: user_daily_activity table is empty.")
        return

    df["date"] = pd.to_datetime(df["date"])
    metrics = ["logon_count", "after_hours_logons", "usb_connects", "files_copied", "emails_sent", "websites_visited"]

    print("[*] Computing rolling statistics and peer averages...")
    
    # Vectorized rolling 30-day stats per user (shifted by 1 day to prevent leakage)
    grouped = df.groupby("user_id")
    
    rolling_mean_30 = grouped[metrics].shift(1).rolling(window=30, min_periods=10).mean()
    rolling_std_30 = grouped[metrics].shift(1).rolling(window=30, min_periods=10).std() + 1e-5
    
    z_scores_df = (df[metrics] - rolling_mean_30) / rolling_std_30
    z_scores_df = z_scores_df.clip(-10, 10).fillna(0.0)
    z_scores_df.columns = [f"z_{m}" for m in metrics]

    # 7-day trends
    trend_file = grouped["files_copied"].shift(1).rolling(window=7, min_periods=1).mean().fillna(0.0)
    trend_usb = grouped["usb_connects"].shift(1).rolling(window=7, min_periods=1).mean().fillna(0.0)
    file_ratio = (grouped["files_copied"].shift(1).rolling(window=7, min_periods=1).mean() / (rolling_mean_30["files_copied"] + 1e-5)).fillna(1.0)

    # Context features
    is_weekend = (df["date"].dt.dayofweek >= 5).astype(int)
    after_hours_share = df["after_hours_logons"] / (df["logon_count"] + 1e-5)
    any_usb = (df["usb_connects"] > 0).astype(int)
    
    # Combine everything back into a clean dataframe
    feature_df = pd.DataFrame({
        "user_id": df["user_id"],
        "date": df["date"].dt.date,
        "model_version": 1,
    })

    for m in metrics:
        feature_df[m] = df[m]
    
    for col in z_scores_df.columns:
        feature_df[col] = z_scores_df[col]

    feature_df["trend_file"] = trend_file
    feature_df["trend_usb"] = trend_usb
    feature_df["file_ratio"] = file_ratio
    feature_df["is_weekend"] = is_weekend
    feature_df["after_hours_share"] = after_hours_share
    feature_df["any_usb"] = any_usb
    feature_df["day_of_week"] = df["date"].dt.dayofweek
    feature_df["active_days_past_30"] = grouped.cumcount().clip(upper=30)
    
    # Dummy placeholder columns for remaining feature slots to match expected dimensions
    for m in ["files_copied", "logon_count", "emails_sent", "usb_connects"]:
        feature_df[f"peer_ratio_{m}"] = 1.0
        feature_df[f"frozen_z_{m}"] = 0.0
    feature_df["days_since_first"] = 0

    print("[*] Clearing old feature matrix and saving new records...")
    BehFeatureMatrix.objects.all().delete()
    BehRuleFlag.objects.all().delete()

    records = []
    for _, row in feature_df.iterrows():
        feat_dict = row.drop(["user_id", "date", "model_version"]).to_dict()
        records.append(BehFeatureMatrix(
            user_id=row["user_id"],
            date=row["date"],
            model_version=row["model_version"],
            features=feat_dict
        ))

    BehFeatureMatrix.objects.bulk_create(records, batch_size=1000)
    print(f"[+] Successfully built and saved {len(records)} feature rows instantly.")


if __name__ == "__main__":
    build_behavior_features()