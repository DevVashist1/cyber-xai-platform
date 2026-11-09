import os
import django
import sys
from pathlib import Path
import pandas as pd
import joblib
from sqlalchemy import create_engine, text

# Setup Django environment
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent / "backend"
sys.path.append(str(BACKEND_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings  # <--- Added missing import
from apps.behavior.models import BehModelRegistry, BehDailyScore

def run_daily_scoring():
    print("[*] Loading trained XGBoost model and feature matrix...")
    artifacts_dir = Path(__file__).resolve().parent.parent / "artifacts"
    model_path = artifacts_dir / "xgboost_behavior_model.joblib"
    feature_path = artifacts_dir / "behavior_features.parquet"

    if not model_path.exists() or not feature_path.exists():
        print("[-] Model or feature artifacts missing. Please train the model first.")
        return

    model = joblib.load(model_path)
    df = pd.read_parquet(feature_path)

    # 1. Register model version in DB if not already present
    model_version = 1
    registry, created = BehModelRegistry.objects.update_or_create(
        model_version=model_version,
        defaults={
            "algorithm": "XGBoost",
            "feature_list": list(model.get_booster().feature_names),
            "date_ranges": {"start": str(df['date'].min()), "end": str(df['date'].max())},
            "metrics": {"status": "trained"},
            "file_reference": str(model_path),
            "is_active": True
        }
    )
    print(f"[+] Model version {model_version} registered in database.")

    # 2. Run inference to compute daily probabilities
    feature_cols = model.get_booster().feature_names
    X = df[feature_cols].fillna(0)
    df['probability'] = model.predict_proba(X)[:, 1]

    # 3. Compute daily rank per user/date and save to beh_daily_score
    print("[*] Computing daily anomaly risk ranks and writing to PostgreSQL...")
    df['rank_in_day'] = df.groupby('date')['probability'].rank(ascending=False, method='min').astype(int)

    db_config = settings.DATABASES['default']
    db_url = f"postgresql+psycopg2://{db_config['USER']}:{db_config['PASSWORD']}@{db_config['HOST']}:{db_config['PORT']}/{db_config['NAME']}"
    engine = create_engine(db_url)

    # Insert batch records cleanly
    score_subset = df[['user_id', 'date', 'probability', 'rank_in_day']].copy()
    score_subset['model_version'] = model_version

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM beh_daily_score WHERE model_version = :ver;"), {"ver": model_version})
    
    score_subset.to_sql('beh_daily_score', engine, if_exists='append', index=False, chunksize=10_000)
    print(f"[+] Successfully wrote {len(score_subset):,} daily scores to PostgreSQL table 'beh_daily_score'!")

if __name__ == "__main__":
    run_daily_scoring()