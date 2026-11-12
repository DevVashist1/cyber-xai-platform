import math
import numpy as np
import pandas as pd
from datetime import datetime
from module4.pipeline.features.feature_registry import BASE_FEATURE_SPECS, TREND_KEY_FEATURES

ATTACK_FAMILY_MAP = {
    "BENIGN": "benign",
    "FTP-Patator": "brute_force",
    "SSH-Patator": "brute_force",
    "DoS slowloris": "dos",
    "DoS Slowloris": "dos",
    "DoS Slowhttptest": "dos",
    "DoS Hulk": "dos",
    "DoS GoldenEye": "dos",
    "Heartbleed": "other",
    "Web Attack - Brute Force": "web_attack",
    "Web Attack - XSS": "web_attack",
    "Web Attack - Sql Injection": "web_attack",
    "Infiltration": "infiltration",
    "Bot": "bot",
    "PortScan": "portscan",
    "DDoS": "ddos",
}

def map_attack_family(raw_lbl: str) -> str:
    if not raw_lbl:
        return "benign"
    s = str(raw_lbl).strip()
    if s in ATTACK_FAMILY_MAP:
        return ATTACK_FAMILY_MAP[s]
    sl = s.lower()
    if "benign" in sl: return "benign"
    if "patator" in sl or ("brute" in sl and "web" not in sl): return "brute_force"
    if "ddos" in sl: return "ddos"
    if "dos" in sl or "slow" in sl or "hulk" in sl or "goldeneye" in sl: return "dos"
    if "portscan" in sl or "port scan" in sl: return "portscan"
    if "bot" in sl: return "bot"
    if "web" in sl or "xss" in sl or "sql" in sl: return "web_attack"
    if "infiltration" in sl: return "infiltration"
    return "other"

def _shannon_entropy_from_counts(counts: np.ndarray) -> float:
    total = counts.sum()
    if total <= 0:
        return 0.0
    probs = counts[counts > 0] / total
    return float(-np.sum(probs * np.log2(probs)))

def summarize_single_window(df_win: pd.DataFrame, win_start: datetime, win_end: datetime,
                            win_size_sec: int, source_day, segment_id: int,
                            seen_src_ips_history: list) -> dict:
    n = len(df_win)
    if n == 0:
        row = {
            "window_size_sec": int(win_size_sec),
            "window_start": win_start,
            "window_end": win_end,
            "source_day": source_day,
            "segment_id": int(segment_id),
            "flow_count": 0,
            "attack_flow_count": 0,
            "attack_share": 0.0,
            "family_counts": {},
            "f_flow_count": 0.0, "f_total_packets": 0.0, "f_total_bytes": 0.0,
            "f_mean_duration": None, "f_median_duration": None,
            "f_uniq_src_ip": 0.0, "f_uniq_dst_ip": 0.0, "f_uniq_dst_port": 0.0, "f_uniq_src_dst_pairs": 0.0,
            "f_ent_src_ip": 0.0, "f_ent_dst_ip": 0.0, "f_ent_dst_port": 0.0,
            "f_top_src_ip_share": 0.0, "f_top_dst_port_share": 0.0,
            "f_share_tcp": 0.0, "f_share_udp": 0.0, "f_share_other_proto": 0.0,
            "f_syn_per_flow": 0.0, "f_rst_per_flow": 0.0, "f_fin_per_flow": 0.0,
            "f_ack_per_flow": 0.0, "f_psh_per_flow": 0.0, "f_urg_per_flow": 0.0,
            "f_share_very_short": 0.0, "f_share_le_2_pkts": 0.0, "f_share_zero_bwd": 0.0,
            "f_mean_pkt_len": None, "f_fwd_bwd_ratio": 1.0,
            "f_novelty_src_ip": 0.0, "f_burstiness": 0.0
        }
        seen_src_ips_history.append(set())
        return row

    fams = df_win["attack_family"].value_counts().to_dict()
    benign_cnt = int(fams.get("benign", 0))
    atk_cnt = int(n - benign_cnt)
    atk_share = float(atk_cnt / n)

    fwd_pkts = df_win["packet_count"].fillna(0).to_numpy(dtype=np.float64)
    bwd_pkts = df_win["total_backward_packets"].fillna(0).to_numpy(dtype=np.float64)
    tot_pkts_arr = fwd_pkts + bwd_pkts
    tot_pkts = float(tot_pkts_arr.sum())

    fwd_bytes = df_win["byte_count"].fillna(0).to_numpy(dtype=np.float64)
    bwd_bytes = df_win["total_length_of_bwd_packets"].fillna(0).to_numpy(dtype=np.float64)
    tot_bytes = float((fwd_bytes + bwd_bytes).sum())

    dur_raw = df_win["duration"].to_numpy(dtype=np.float64)
    valid_dur = dur_raw[(~np.isnan(dur_raw)) & (dur_raw >= 0)]
    mean_dur = float(np.mean(valid_dur)) if len(valid_dur) > 0 else 0.0
    med_dur = float(np.median(valid_dur)) if len(valid_dur) > 0 else 0.0

    src_counts = df_win["src_ip"].value_counts()
    dst_counts = df_win["dst_ip"].value_counts()
    port_counts = df_win["destination_port"].value_counts()

    uniq_src = float(len(src_counts))
    uniq_dst = float(len(dst_counts))
    uniq_port = float(len(port_counts))
    uniq_pairs = float(df_win.groupby(["src_ip", "dst_ip"], sort=False).ngroups)

    ent_src = _shannon_entropy_from_counts(src_counts.to_numpy())
    ent_dst = _shannon_entropy_from_counts(dst_counts.to_numpy())
    ent_port = _shannon_entropy_from_counts(port_counts.to_numpy())

    top_src_share = float(src_counts.iloc[0] / n) if len(src_counts) > 0 else 0.0
    top_port_share = float(port_counts.iloc[0] / n) if len(port_counts) > 0 else 0.0

    proto = df_win["protocol"].fillna(0).to_numpy(dtype=np.int32)
    share_tcp = float(np.sum(proto == 6) / n)
    share_udp = float(np.sum(proto == 17) / n)
    share_other = float(max(0.0, 1.0 - share_tcp - share_udp))

    syn_pf = float(df_win["syn_flag_count"].fillna(0).mean())
    rst_pf = float(df_win["rst_flag_count"].fillna(0).mean())
    fin_pf = float(df_win["fin_flag_count"].fillna(0).mean())
    ack_pf = float(df_win["ack_flag_count"].fillna(0).mean())
    psh_pf = float(df_win["psh_flag_count"].fillna(0).mean())
    urg_pf = float(df_win["urg_flag_count"].fillna(0).mean())

    share_vshort = float(np.sum((valid_dur >= 0) & (valid_dur < 1000.0)) / max(1, len(valid_dur)))
    share_le2 = float(np.sum(tot_pkts_arr <= 2) / n)
    share_zero_bwd = float(np.sum(bwd_pkts == 0) / n)
    mean_pkt_l = float(df_win["packet_length_mean"].fillna(0).mean())
    fwd_bwd_rat = float((fwd_pkts.sum() + 1.0) / (bwd_pkts.sum() + 1.0))

    cur_src_set = set(src_counts.index)
    if seen_src_ips_history:
        past_union = set().union(*seen_src_ips_history[-5:])
        unseen = len(cur_src_set - past_union)
        novelty = float(unseen / max(1, len(cur_src_set)))
    else:
        novelty = 1.0
    seen_src_ips_history.append(cur_src_set)

    sec_bins = df_win["assign_ts"].dt.floor("s").value_counts()
    if len(sec_bins) > 1:
        arr_std = float(sec_bins.std(ddof=0))
        arr_mean = float(sec_bins.mean())
        burstiness = float(arr_std / (arr_mean + 1e-6))
    else:
        burstiness = 0.0

    return {
        "window_size_sec": int(win_size_sec),
        "window_start": win_start,
        "window_end": win_end,
        "source_day": source_day,
        "segment_id": int(segment_id),
        "flow_count": int(n),
        "attack_flow_count": atk_cnt,
        "attack_share": round(atk_share, 6),
        "family_counts": {str(k): int(v) for k, v in fams.items()},
        "f_flow_count": float(n),
        "f_total_packets": tot_pkts,
        "f_total_bytes": tot_bytes,
        "f_mean_duration": mean_dur,
        "f_median_duration": med_dur,
        "f_uniq_src_ip": uniq_src,
        "f_uniq_dst_ip": uniq_dst,
        "f_uniq_dst_port": uniq_port,
        "f_uniq_src_dst_pairs": uniq_pairs,
        "f_ent_src_ip": ent_src,
        "f_ent_dst_ip": ent_dst,
        "f_ent_dst_port": ent_port,
        "f_top_src_ip_share": top_src_share,
        "f_top_dst_port_share": top_port_share,
        "f_share_tcp": share_tcp,
        "f_share_udp": share_udp,
        "f_share_other_proto": share_other,
        "f_syn_per_flow": syn_pf,
        "f_rst_per_flow": rst_pf,
        "f_fin_per_flow": fin_pf,
        "f_ack_per_flow": ack_pf,
        "f_psh_per_flow": psh_pf,
        "f_urg_per_flow": urg_pf,
        "f_share_very_short": share_vshort,
        "f_share_le_2_pkts": share_le2,
        "f_share_zero_bwd": share_zero_bwd,
        "f_mean_pkt_len": mean_pkt_l,
        "f_fwd_bwd_ratio": fwd_bwd_rat,
        "f_novelty_src_ip": novelty,
        "f_burstiness": burstiness
    }

def compute_engineered_features_per_segment(df_base: pd.DataFrame, L: int = 5) -> pd.DataFrame:
    df = df_base.sort_values(["segment_id", "window_start"]).copy().reset_index(drop=True)
    base_cols = [c[0] for c in BASE_FEATURE_SPECS]
    for col in base_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    new_cols = {}
    for seg_id, grp in df.groupby("segment_id", sort=False):
        idx = grp.index
        for col in TREND_KEY_FEATURES:
            s = grp[col]
            l1 = s.shift(1)
            l2 = s.shift(2)
            l3 = s.shift(3)
            diff1 = s - l1
            ratio1 = (s + 1e-4) / (l1.abs() + 1e-4)
            rmean = l1.rolling(window=L, min_periods=L).mean()
            rstd = l1.rolling(window=L, min_periods=L).std(ddof=0).fillna(0.0)
            zscore = (s - rmean) / (rstd + 1e-5)
            slope5 = (-2.0 * s.shift(4) - 1.0 * l3 + 1.0 * l1 + 2.0 * s) / 10.0

            for k_name, series_val in [
                (f"{col}_lag1", l1), (f"{col}_lag2", l2), (f"{col}_lag3", l3),
                (f"{col}_diff1", diff1), (f"{col}_ratio1", ratio1),
                (f"{col}_roll_mean", rmean), (f"{col}_roll_z", zscore), (f"{col}_slope5", slope5)
            ]:
                if k_name not in new_cols:
                    new_cols[k_name] = pd.Series(index=df.index, dtype=np.float64)
                new_cols[k_name].loc[idx] = series_val

    eng_df = pd.DataFrame(new_cols, index=df.index)
    return pd.concat([df, eng_df], axis=1)
