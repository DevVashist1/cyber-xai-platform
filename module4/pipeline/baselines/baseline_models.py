import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

def persistence_baseline(df_slice):
    return df_slice["is_surge"].to_numpy(dtype=np.float32)

def rolling_share_baseline(df_slice, window_L=3):
    return df_slice["attack_share"].shift(1).rolling(window_L, min_periods=1).mean().fillna(0.0).to_numpy(dtype=np.float32)

def traffic_logistic_baseline(X_train, y_train, X_eval, seed=42):
    scaler = StandardScaler()
    X_tr = scaler.fit_transform(X_train)
    X_ev = scaler.transform(X_eval)
    clf = LogisticRegression(max_iter=500, class_weight="balanced", random_state=seed)
    clf.fit(X_tr, y_train)
    return clf.predict_proba(X_ev)[:, 1]
