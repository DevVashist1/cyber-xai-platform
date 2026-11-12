BASE_FEATURE_SPECS = [
    ("f_flow_count", "Flow Count", "volume", "Total network flows ending in the window", "higher_is_riskier"),
    ("f_total_packets", "Total Packets", "volume", "Sum of forward and backward packets across flows", "higher_is_riskier"),
    ("f_total_bytes", "Total Bytes", "volume", "Sum of forward and backward payload bytes", "higher_is_riskier"),
    ("f_mean_duration", "Mean Flow Duration (us)", "volume", "Mean flow duration in microseconds (excluding negative/null)", "context_dependent"),
    ("f_median_duration", "Median Flow Duration (us)", "volume", "Median flow duration in microseconds", "context_dependent"),
    ("f_uniq_src_ip", "Unique Source IPs", "diversity", "Count of distinct source IP addresses in the window", "context_dependent"),
    ("f_uniq_dst_ip", "Unique Destination IPs", "diversity", "Count of distinct destination IP addresses", "context_dependent"),
    ("f_uniq_dst_port", "Unique Destination Ports", "diversity", "Count of distinct destination ports targeted", "higher_is_riskier"),
    ("f_uniq_src_dst_pairs", "Unique Src-Dst Pairs", "diversity", "Count of distinct (source IP, destination IP) pairs", "context_dependent"),
    ("f_ent_src_ip", "Source IP Entropy", "concentration", "Shannon entropy of source IP distribution", "lower_is_riskier"),
    ("f_ent_dst_ip", "Destination IP Entropy", "concentration", "Shannon entropy of destination IP distribution", "lower_is_riskier"),
    ("f_ent_dst_port", "Destination Port Entropy", "concentration", "Shannon entropy of destination port distribution", "context_dependent"),
    ("f_top_src_ip_share", "Top Source IP Share", "concentration", "Fraction of flows originating from the single busiest source IP", "higher_is_riskier"),
    ("f_top_dst_port_share", "Top Destination Port Share", "concentration", "Fraction of flows targeting the single busiest destination port", "higher_is_riskier"),
    ("f_share_tcp", "TCP Share", "shape", "Fraction of flows using TCP (protocol 6)", "context_dependent"),
    ("f_share_udp", "UDP Share", "shape", "Fraction of flows using UDP (protocol 17)", "context_dependent"),
    ("f_share_other_proto", "Other Protocol Share", "shape", "Fraction of flows using neither TCP nor UDP", "context_dependent"),
    ("f_syn_per_flow", "SYN Flags per Flow", "flags", "Mean SYN flag count per flow in the window", "higher_is_riskier"),
    ("f_rst_per_flow", "RST Flags per Flow", "flags", "Mean RST flag count per flow in the window", "higher_is_riskier"),
    ("f_fin_per_flow", "FIN Flags per Flow", "flags", "Mean FIN flag count per flow in the window", "context_dependent"),
    ("f_ack_per_flow", "ACK Flags per Flow", "flags", "Mean ACK flag count per flow in the window", "context_dependent"),
    ("f_psh_per_flow", "PSH Flags per Flow", "flags", "Mean PSH flag count per flow in the window", "context_dependent"),
    ("f_urg_per_flow", "URG Flags per Flow", "flags", "Mean URG flag count per flow in the window", "higher_is_riskier"),
    ("f_share_very_short", "Share of Very Short Flows", "shape", "Fraction of flows with duration under 1000 microseconds", "higher_is_riskier"),
    ("f_share_le_2_pkts", "Share of Tiny Flows (<=2 Pkts)", "shape", "Fraction of flows with 2 or fewer total packets", "higher_is_riskier"),
    ("f_share_zero_bwd", "Share of Zero-Backward Flows", "shape", "Fraction of flows with zero backward response packets", "higher_is_riskier"),
    ("f_mean_pkt_len", "Mean Packet Length", "shape", "Mean packet length across flows in the window", "context_dependent"),
    ("f_fwd_bwd_ratio", "Fwd/Bwd Packet Ratio", "shape", "Ratio of total forward packets to backward packets (+1 smoothed)", "higher_is_riskier"),
    ("f_novelty_src_ip", "Unseen Source IP Share", "novelty", "Fraction of source IPs not observed in the previous N windows of the segment", "higher_is_riskier"),
    ("f_burstiness", "Intra-Window Arrival Burstiness", "trend", "Coefficient of variation of per-second flow arrivals within the window", "higher_is_riskier"),
]

TREND_KEY_FEATURES = [
    "f_flow_count", "f_total_packets", "f_uniq_dst_port", "f_ent_src_ip",
    "f_ent_dst_port", "f_top_src_ip_share", "f_syn_per_flow", "f_rst_per_flow",
    "f_share_very_short", "f_share_le_2_pkts", "f_share_zero_bwd", "f_novelty_src_ip"
]

FORBIDDEN_FEATURE_NAMES = {
    "attack_flow_count", "attack_share", "family_counts", "attack_label",
    "attack_label_raw", "attack_family", "src_ip", "dst_ip", "source_ip",
    "destination_ip", "source_port", "destination_port", "hour", "weekday", "day_of_week"
}
