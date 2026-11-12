import json
import uuid
import numpy as np
import pandas as pd

def compute_surge_and_horizon_labels(df_win: pd.DataFrame, share_threshold: float = 0.20,
                                     flow_floor: int = 15, horizon_k: int = 3, calm_C: int = 3) -> pd.DataFrame:
    df = df_win.sort_values(["segment_id", "window_start"]).copy().reset_index(drop=True)
    df["is_surge"] = ((df["attack_share"] >= share_threshold) & (df["flow_count"] >= flow_floor)).astype(int)

    df["y"] = 0
    df["is_calm"] = False
    df["onset_flag"] = False
    df["valid_horizon"] = True

    for seg_id, grp in df.groupby("segment_id", sort=False):
        idx = grp.index.to_numpy()
        surges = grp["is_surge"].to_numpy()
        n = len(idx)
        y_arr = np.zeros(n, dtype=int)
        calm_arr = np.zeros(n, dtype=bool)
        valid_h = np.ones(n, dtype=bool)

        for i in range(n):
            if i + horizon_k >= n:
                valid_h[i] = False
            else:
                y_arr[i] = 1 if np.any(surges[i + 1 : i + 1 + horizon_k] == 1) else 0

            prev_start = max(0, i - calm_C)
            if surges[i] == 0 and not np.any(surges[prev_start:i] == 1):
                calm_arr[i] = True

        df.loc[idx, "y"] = y_arr
        df.loc[idx, "is_calm"] = calm_arr
        df.loc[idx, "onset_flag"] = calm_arr & (y_arr == 1)
        df.loc[idx, "valid_horizon"] = valid_h

    return df

def extract_surge_episodes(df_labeled: pd.DataFrame, config_id: str = "default") -> list:
    episodes = []
    for seg_id, grp in df_labeled.sort_values("window_start").groupby("segment_id", sort=False):
        in_ep = False
        ep_rows = []
        for _, r in grp.iterrows():
            if int(r["is_surge"]) == 1:
                in_ep = True
                ep_rows.append(r)
            else:
                if in_ep and ep_rows:
                    episodes.append(_pack_episode(ep_rows, config_id))
                    ep_rows = []
                in_ep = False
        if in_ep and ep_rows:
            episodes.append(_pack_episode(ep_rows, config_id))
    return episodes

def _pack_episode(ep_rows: list, config_id: str) -> dict:
    fams = {}
    for r in ep_rows:
        fc = r.get("family_counts") or {}
        if isinstance(fc, str):
            try:
                fc = json.loads(fc)
            except Exception:
                fc = {}
        if isinstance(fc, dict):
            for k, v in fc.items():
                if k != "benign":
                    fams[k] = fams.get(k, 0) + int(v)
    return {
        "episode_id": str(uuid.uuid4()),
        "config_id": config_id,
        "window_size_sec": int(ep_rows[0]["window_size_sec"]),
        "source_day": ep_rows[0]["source_day"],
        "start_window": ep_rows[0]["window_start"],
        "end_window": ep_rows[-1]["window_end"],
        "n_windows": len(ep_rows),
        "peak_attack_share": float(max(r["attack_share"] for r in ep_rows)),
        "families": fams
    }

def assign_scheme_a_splits(df_labeled: pd.DataFrame, horizon_k: int = 3, warm_up_L: int = 5) -> pd.DataFrame:
    df = df_labeled.copy()
    df["split_role"] = "excluded"

    for seg_id, grp in df.groupby("segment_id", sort=False):
        valid_grp = grp[grp["valid_horizon"]].copy()
        idx = valid_grp.index.to_numpy()
        surges = valid_grp["is_surge"].to_numpy()
        n = len(idx)
        if n <= warm_up_L + 10:
            continue

        usable_idx = idx[warm_up_L:]
        usable_surges = surges[warm_up_L:]
        m = len(usable_idx)

        b1 = int(m * 0.60)
        b2 = int(m * 0.80)

        while b1 < m - 10 and usable_surges[b1] == 1:
            b1 += 1
        while b2 < m - 5 and (b2 <= b1 + horizon_k or usable_surges[b2] == 1):
            b2 += 1

        train_end = max(0, b1 - horizon_k)
        val_start = b1
        val_end = max(val_start, b2 - horizon_k)
        test_start = b2

        df.loc[usable_idx[:train_end], "split_role"] = "train"
        df.loc[usable_idx[train_end:val_start], "split_role"] = "purged"
        df.loc[usable_idx[val_start:val_end], "split_role"] = "val"
        df.loc[usable_idx[val_end:test_start], "split_role"] = "purged"
        df.loc[usable_idx[test_start:], "split_role"] = "test"

    return df
