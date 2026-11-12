import numpy as np
import pandas as pd
from datetime import date
from django.db import connection
from module4.pipeline.windowing.build_windows import map_attack_family, summarize_single_window

def load_and_amend_day_flows(source_day_keys: list, cal_date: date) -> pd.DataFrame:
    placeholders = ",".join(["%s"] * len(source_day_keys))
    query = f"""
        SELECT src_ip, dst_ip, destination_port, protocol, timestamp, duration,
               packet_count, total_backward_packets, byte_count, total_length_of_bwd_packets,
               fin_flag_count, syn_flag_count, rst_flag_count, psh_flag_count, ack_flag_count, urg_flag_count,
               packet_length_mean, attack_label
        FROM network_flows_clean
        WHERE source_day IN ({placeholders})
    """
    with connection.cursor() as cur:
        cur.execute(query, source_day_keys)
        rows = cur.fetchall()
    cols = [
        "src_ip", "dst_ip", "destination_port", "protocol", "timestamp", "duration",
        "packet_count", "total_backward_packets", "byte_count", "total_length_of_bwd_packets",
        "fin_flag_count", "syn_flag_count", "rst_flag_count", "psh_flag_count", "ack_flag_count", "urg_flag_count",
        "packet_length_mean", "attack_label"
    ]
    df = pd.DataFrame(rows, columns=cols)
    if df.empty:
        return df

    ts = pd.to_datetime(df["timestamp"])
    afternoon_mask = ts.dt.hour.isin([1, 2, 3, 4, 5, 6, 7])
    ts = ts.where(~afternoon_mask, ts + pd.Timedelta(hours=12))
    df["start_ts"] = ts

    dur_us = pd.to_numeric(df["duration"], errors="coerce").fillna(0.0)
    safe_dur_sec = np.where(dur_us > 0, np.minimum(dur_us / 1e6, 3600.0), 0.0)
    df["assign_ts"] = df["start_ts"] + pd.to_timedelta(safe_dur_sec, unit="s")
    df["attack_family"] = df["attack_label"].map(map_attack_family)
    df["cal_date"] = cal_date
    return df

def build_windows_for_day(df_day: pd.DataFrame, cal_date: date, segment_id: int, win_sizes=(60, 300, 600)) -> dict:
    results = {w: [] for w in win_sizes}
    if df_day.empty:
        return results

    min_ts = df_day["assign_ts"].min().floor("10min")
    max_ts = df_day["assign_ts"].max().ceil("10min")

    for w in win_sizes:
        freq_str = f"{w}s"
        df_day["win_bin"] = df_day["assign_ts"].dt.floor(freq_str)
        grouped = {k: grp for k, grp in df_day.groupby("win_bin", sort=False)}
        grid = pd.date_range(start=min_ts, end=max_ts, freq=freq_str)
        seen_hist = []
        for w_start in grid:
            w_end = w_start + pd.Timedelta(seconds=w)
            sub = grouped.get(w_start)
            if sub is None:
                sub = df_day.iloc[0:0]
            w_row = summarize_single_window(sub, w_start.to_pydatetime(), w_end.to_pydatetime(), w, cal_date, segment_id, seen_hist)
            results[w].append(w_row)
    return results
