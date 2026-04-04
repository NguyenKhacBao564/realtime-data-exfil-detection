"""
src/features/window_features.py — Extract features from a packet window per source IP.
"""

import numpy as np
from typing import Dict, List, Any

# Thresholds
MIN_PAYLOAD_FOR_BURST = 10   # bytes — ignore tiny ACK packets
BURST_IAT_THRESHOLD   = 0.1  # seconds — inter-arrival < this = burst


def _detect_packet_direction(pkt: Dict) -> str:
    """
    Detect if a packet is forward (client→server) or backward (server→client).
    Uses TCP flags heuristic:
      - First SYN (no ACK) from flow initiator → forward
      - SYN+ACK response → backward
      - Established connection: use src_port pattern
    Falls back to src_ip comparison.
    """
    tcp_flags = pkt.get("tcp_flags", {})

    # SYN-only packet = flow initiator → forward
    if tcp_flags.get("SYN") and not tcp_flags.get("ACK"):
        return "fwd"
    # SYN+ACK = response → backward
    if tcp_flags.get("SYN") and tcp_flags.get("ACK"):
        return "bwd"
    # RST/FIN = end of flow, direction preserved
    if tcp_flags.get("RST") or tcp_flags.get("FIN"):
        return pkt.get("direction", "fwd")

    # Fallback: known client ports (ephemeral range)
    src_port = pkt.get("src_port", 0)
    dst_port = pkt.get("dst_port", 0)
    if src_port > 49152:
        # Source is ephemeral (client) → forward
        return "fwd"
    elif dst_port > 49152:
        # Destination is ephemeral → backward
        return "bwd"

    # Generic fallback
    return "fwd"


def extract_window_features(packets: List[Dict], src_ip: str, window_start: float) -> Dict[str, Any]:
    """
    Extract aggregated features from a list of packets belonging to one src_ip in a time window.

    Args:
        packets: List of packet dicts (from packet_parser.py)
        src_ip: Source IP address
        window_start: Unix timestamp of window start

    Returns:
        Feature dict for this window, or None if too few packets.
    """
    if len(packets) < 3:
        return None

    # Sort by timestamp
    packets = sorted(packets, key=lambda p: p["timestamp"])

    # Assign directions to each packet using heuristic
    for pkt in packets:
        pkt["direction"] = _detect_packet_direction(pkt)

    # Basic packet counts
    n_fwd = sum(1 for p in packets if p.get("direction", "fwd") == "fwd")
    n_bwd = len(packets) - n_fwd

    # Extract arrays for vectorized computation
    timestamps = np.array([p["timestamp"] for p in packets])
    payload_lens = np.array([p.get("payload_len", 0) for p in packets])
    dst_ports    = np.array([p.get("dst_port", 0) for p in packets])
    pkt_lens     = np.array([p.get("pkt_len", 0) for p in packets])

    # Duration
    duration = timestamps[-1] - timestamps[0] if len(timestamps) > 1 else 0.0
    window_duration = (timestamps[-1] - window_start) if len(timestamps) > 0 else 0.0

    # Forward vs backward bytes
    fwd_payloads = np.array([p.get("payload_len", 0) for p in packets
                              if p.get("direction", "fwd") == "fwd"])
    bwd_payloads = np.array([p.get("payload_len", 0) for p in packets
                              if p.get("direction", "fwd") == "bwd"])

    total_fwd_bytes = int(fwd_payloads.sum())
    total_bwd_bytes = int(bwd_payloads.sum())
    total_bytes     = total_fwd_bytes + total_bwd_bytes

    # Upload ratio
    upload_ratio = total_fwd_bytes / max(total_bwd_bytes, 1)

    # Inter-arrival times
    if len(timestamps) > 1:
        iats = np.diff(timestamps)
    else:
        iats = np.array([0.0])

    # Burst detection: inter-arrival < BURST_IAT_THRESHOLD (all packets)
    burst_mask = iats < BURST_IAT_THRESHOLD
    burst_count = int(burst_mask.sum())
    burst_ratio = burst_count / max(len(iats), 1)

    # Also count bursts in forward direction only (upload direction)
    if len(timestamps) > 1:
        fwd_iats = np.array([
            timestamps[i+1] - timestamps[i]
            for i in range(len(timestamps)-1)
            if packets[i].get("direction", "fwd") == "fwd"
        ])
        fwd_burst_count = int((fwd_iats < BURST_IAT_THRESHOLD).sum())
        # For backward burst, use the smaller value (less relevant for exfil)
        bwd_burst_count = burst_count - fwd_burst_count
        bwd_burst_count = max(0, bwd_burst_count)
    else:
        fwd_burst_count = 0
        bwd_burst_count = 0

    # Use forward burst count as the primary metric for exfil detection
    # (exfil = uploading data = forward direction)
    burst_count = fwd_burst_count
    burst_ratio = burst_count / max(len(fwd_iats), 1)

    # Unusual ports — flag ports that are suspicious for exfiltration.
    # PCAP captured from victim/server side: dst_port = client ephemeral (high port)
    # and src_port = server port. We check src_port for suspicious server ports.
    # For legitimate HTTP traffic (PCAP from victim side):
    #   - src_port should be in {80, 443, 8080, 8443, 53, ...}
    #   - dst_port = client ephemeral = normal
    # Suspicious = server port that is NOT a common service port
    SERVER_PORTS = {80, 443, 8080, 8443, 53, 22, 21, 25, 110, 143, 993, 995, 587, 465}
    src_ports = np.array([p.get("src_port", 0) for p in packets])
    unusual_srv_count = sum(1 for p in src_ports
                            if int(p) > 0 and int(p) not in SERVER_PORTS)
    unusual_port_ratio = unusual_srv_count / max(len(src_ports), 1)

    # Request rate
    requests_per_second = len(packets) / max(duration, 0.001)

    # Inter-request time stats
    iat_mean = float(iats.mean()) if len(iats) > 0 else 0.0
    iat_std  = float(iats.std())  if len(iats) > 1 else 0.0
    iat_min  = float(iats.min()) if len(iats) > 0 else 0.0
    iat_max  = float(iats.max()) if len(iats) > 0 else 0.0

    # Payload size stats
    payload_mean = float(payload_lens.mean()) if len(payload_lens) > 0 else 0.0
    payload_std  = float(payload_lens.std())  if len(payload_lens) > 1 else 0.0
    payload_max  = float(payload_lens.max()) if len(payload_lens) > 0 else 0.0

    # Packet length stats
    pkt_mean = float(pkt_lens.mean()) if len(pkt_lens) > 0 else 0.0
    pkt_std  = float(pkt_lens.std())  if len(pkt_lens) > 1 else 0.0

    # TCP flags
    total_psh = sum(1 for p in packets if p.get("tcp_flags", {}).get("PSH", False))
    total_ack = sum(1 for p in packets if p.get("tcp_flags", {}).get("ACK", False))
    total_syn = sum(1 for p in packets if p.get("tcp_flags", {}).get("SYN", False))
    total_fin = sum(1 for p in packets if p.get("tcp_flags", {}).get("FIN", False))
    total_rst = sum(1 for p in packets if p.get("tcp_flags", {}).get("RST", False))

    # Unique destinations
    unique_dsts = len(set(p.get("dst_ip", "") for p in packets))

    # Is long session
    is_long_session = 1 if window_duration > 300 else 0

    features = {
        # Counts
        "request_count":        len(packets),
        "total_fwd_bytes":      total_fwd_bytes,
        "total_bwd_bytes":      total_bwd_bytes,
        "total_bytes":          total_bytes,

        # Ratios
        "upload_download_ratio": upload_ratio,
        "burst_count":          burst_count,
        "fwd_burst_count":      fwd_burst_count,
        "burst_ratio":          burst_ratio,
        "unusual_port_ratio":   unusual_port_ratio,

        # Timing
        "request_rate":          requests_per_second,
        "inter_request_time_mean": iat_mean,
        "inter_request_time_std":  iat_std,
        "inter_request_time_min":  iat_min,
        "inter_request_time_max":  iat_max,
        "window_duration":       window_duration,

        # Payload stats
        "mean_payload_size":     payload_mean,
        "std_payload_size":      payload_std,
        "max_payload_size":      payload_max,

        # Packet stats
        "mean_packet_size":      pkt_mean,
        "std_packet_size":       pkt_std,

        # TCP flags
        "psh_flag_count": total_psh,
        "ack_flag_count": total_ack,
        "syn_flag_count": total_syn,
        "fin_flag_count": total_fin,
        "rst_flag_count": total_rst,

        # Destinations
        "unique_destinations": unique_dsts,

        # Session type
        "is_long_session": is_long_session,

        # Meta
        "src_ip": src_ip,
        "window_start": window_start,
    }

    return features


def extract_window_features_from_csv_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract features from a CICFlowMeter CSV row (for model training).
    Maps CSV columns → pipeline feature keys.

    Args:
        row: Dict of {column_name: value}

    Returns:
        Feature dict compatible with pipeline feature vector.
    """
    import numpy as np

    def safe(col):
        val = row.get(col, 0)
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return 0.0
        if isinstance(val, str):
            return 0.0
        return float(val)

    fwd_bytes = safe("Total Length of Fwd Packets")
    bwd_bytes = safe("Total Length of Bwd Packets")
    duration  = safe("Flow Duration") / 1_000_000  # microseconds → seconds

    return {
        "request_count":         int(safe("Total Fwd Packets") + safe("Total Backward Packets")),
        "total_fwd_bytes":       int(fwd_bytes),
        "total_bwd_bytes":       int(bwd_bytes),
        "total_bytes":           int(fwd_bytes + bwd_bytes),
        "upload_download_ratio": fwd_bytes / max(bwd_bytes, 1),
        "burst_count":           0,  # Not available from CSV (needs raw packets)
        "burst_ratio":           0.0,
        "unusual_port_ratio":    0.0,  # Computed at pipeline time
        "request_rate":          safe("Flow Packets/s"),
        "inter_request_time_mean": safe("Flow IAT Mean") / 1_000_000,
        "inter_request_time_std":  safe("Flow IAT Std") / 1_000_000,
        "inter_request_time_min":  safe("Flow IAT Min") / 1_000_000,
        "inter_request_time_max":  safe("Flow IAT Max") / 1_000_000,
        "window_duration":        duration,
        "mean_payload_size":      safe("Average Packet Size"),
        "std_payload_size":       safe("Packet Length Std"),
        "max_payload_size":       safe("Max Packet Length"),
        "mean_packet_size":       safe("Average Packet Size"),
        "std_packet_size":        safe("Packet Length Std"),
        "psh_flag_count":         int(safe("PSH Flag Count")),
        "ack_flag_count":         int(safe("ACK Flag Count")),
        "syn_flag_count":         int(safe("SYN Flag Count")),
        "fin_flag_count":         int(safe("FIN Flag Count")),
        "rst_flag_count":         int(safe("RST Flag Count")),
        "unique_destinations":     1,  # Unknown from single row
        "is_long_session":        1 if duration > 300 else 0,
    }
