import subprocess
import sys
import json
import numpy as np
from pathlib import Path
from sklearn.linear_model import LogisticRegression
import xgboost as xgb


def train_xgboost_native(X_train, y_train, spw: float = 1.0, seed: int = 42, save_path: Path = None):
    model = xgb.XGBClassifier(
        max_depth=3, learning_rate=0.05, n_estimators=160,
        subsample=0.8, colsample_bytree=0.8, min_child_weight=5,
        reg_lambda=2.0, scale_pos_weight=spw, random_state=seed, eval_metric="aucpr"
    )
    model.fit(X_train, y_train)
    if save_path:
        model.get_booster().save_model(str(save_path))
    return model


def train_lightgbm_native(X_train, y_train, X_val, X_test, feature_names: list, spw: float = 1.0, seed: int = 42, save_path: Path = None):
    """Train genuine LightGBM model via isolated CLI/SVM file so Windows NumPy 2.x int32 pointer bug never triggers."""
    tmp_dir = Path("module4/artifacts")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    npz_in = tmp_dir / "_lgb_input.npz"
    npz_out = tmp_dir / "_lgb_output.npz"
    np.savez(npz_in, X_train=X_train, y_train=y_train, X_val=X_val, X_test=X_test)

    worker_code = f"""
import numpy as np
import lightgbm as lgb
from sklearn.datasets import dump_svmlight_file

data = np.load(r"{npz_in}")
X_tr, y_tr = data["X_train"], data["y_train"]
X_va, X_te = data["X_val"], data["X_test"]
svm_tr = r"{tmp_dir / '_train.svm'}"
dump_svmlight_file(X_tr, y_tr.astype(np.float64), svm_tr, zero_based=True)

dtrain = lgb.Dataset(svm_tr, free_raw_data=False)
dtrain.set_feature_name({json.dumps(feature_names)})
params = {{
    "objective": "binary",
    "metric": "auc",
    "num_leaves": 7,
    "max_depth": 3,
    "learning_rate": 0.05,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "min_data_in_leaf": 15,
    "lambda_l2": 2.0,
    "scale_pos_weight": {float(spw)},
    "seed": {int(seed)},
    "verbose": -1,
    "num_threads": 1
}}
bst = lgb.train(params, dtrain, num_boost_round=120)
bst.save_model(r"{save_path}")
val_p = bst.predict(X_va.tolist())
test_p = bst.predict(X_te.tolist())
np.savez(r"{npz_out}", val_p=val_p, test_p=test_p)
"""
    res = subprocess.run([sys.executable, "-c", worker_code], capture_output=True, text=True)
    for f in [npz_in, tmp_dir / "_train.svm"]:
        if f.exists():
            f.unlink()
    if res.returncode == 0 and npz_out.exists():
        out = np.load(npz_out)
        val_p, test_p = out["val_p"], out["test_p"]
        npz_out.unlink()
        return val_p, test_p
    raise RuntimeError(f"LightGBM training failed: {res.stderr}")


def fit_platt_calibrator(val_raw_probs: np.ndarray, y_val: np.ndarray) -> tuple:
    logits = np.log(np.clip(val_raw_probs, 1e-6, 1 - 1e-6) / (1.0 - np.clip(val_raw_probs, 1e-6, 1 - 1e-6))).reshape(-1, 1)
    if len(np.unique(y_val)) > 1:
        lr = LogisticRegression(random_state=42)
        lr.fit(logits, y_val)
        return float(lr.coef_[0][0]), float(lr.intercept_[0])
    return 1.0, 0.0
