"""
src/capture/packet_parser.py — Parse Scapy packet → dict for pipeline.
"""

from scapy.all import IP, TCP, UDP, Raw
from typing import Optional


def parse_packet(pkt) -> Optional[dict]:
    """
    Parse a Scapy packet into a dict suitable for the pipeline queue.

    Args:
        pkt: Scapy packet object

    Returns:
        Dict with packet fields, or None if packet is not TCP/IP or is invalid.
    """
    # Only process IP packets
    if not pkt.haslayer(IP):
        return None

    ip_layer = pkt[IP]

    # Determine protocol
    proto = ip_layer.proto  # 6=TCP, 17=UDP

    # Build base dict
    result = {
        "timestamp": float(pkt.time),
        "src_ip":    str(ip_layer.src),
        "dst_ip":    str(ip_layer.dst),
        "pkt_len":   len(pkt),
        "protocol":   {6: "TCP", 17: "UDP"}.get(proto, f"proto-{proto}"),
    }

    # TCP parsing
    if pkt.haslayer(TCP):
        tcp = pkt[TCP]
        result["src_port"]    = int(tcp.sport)
        result["dst_port"]    = int(tcp.dport)
        result["payload_len"] = max(0, len(pkt[TCP].payload))
        result["flags"]        = tcp.flags.value if hasattr(tcp.flags, "value") else str(tcp.flags)
        result["tcp_flags"]    = {
            "FIN": tcp.flags.F,
            "SYN": tcp.flags.S,
            "RST": tcp.flags.R,
            "PSH": tcp.flags.P,
            "ACK": tcp.flags.A,
            "URG": tcp.flags.U,
        }
    # UDP parsing
    elif pkt.haslayer(UDP):
        udp = pkt[UDP]
        result["src_port"]    = int(udp.sport)
        result["dst_port"]    = int(udp.dport)
        result["payload_len"] = max(0, len(pkt[UDP].payload))
        result["flags"]       = "UDP"
        result["tcp_flags"]    = {}
    else:
        # Not TCP/UDP — skip
        return None

    return result


def is_http_port(port: int, http_ports: list) -> bool:
    """Check if port is an HTTP-related port."""
    return port in http_ports


def packet_summary(pkt_dict: dict) -> str:
    """Human-readable summary of a packet dict."""
    return (
        f"{pkt_dict['timestamp']:.3f}  "
        f"{pkt_dict['src_ip']}:{pkt_dict['src_port']} → "
        f"{pkt_dict['dst_ip']}:{pkt_dict['dst_port']}  "
        f"[{pkt_dict['protocol']}]  "
        f"len={pkt_dict['pkt_len']}  payload={pkt_dict.get('payload_len', 0)}"
    )
