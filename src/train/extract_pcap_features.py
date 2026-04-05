"""
src/train/extract_pcap_features.py — Extract flow-level features from self-captured PCAP files.

Output format compatible with CICIDS2017 features so it can be merged
with the existing processed data or used standalone for ground-truth evaluation.
"""

import sys
import os
import json
import warnings
from pathlib import Path

import pandas as pd
import numpy as np
from scapy.all import rdpcap, IP, TCP, Raw

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def packet_to_flow_dict(pkt):
    """Convert Scapy packet → flow dict. Returns None if not TCP/IP."""
    if not pkt.haslayer(IP) or not pkt.haslayer(TCP):
        return None

    src_ip  = pkt[IP].src
    dst_ip  = pkt[IP].dst
    sport   = pkt[TCP].sport
    dport   = pkt[TCP].dport

    # Payload length
    if pkt.haslayer(Raw):
        payload_len = len(pkt[TCP].payload)
    else:
        payload_len = 0

    # TCP flags as boolean values
    flags = pkt[TCP].flags
    f_syn  = 1 if 'S' in str(flags) else 0
    f_fin  = 1 if 'F' in str(flags) else 0
    f_rst  = 1 if 'R' in str(flags) else 0
    f_ack  = 1 if 'A' in str(flags) else 0
    f_psh  = 1 if 'P' in str(flags) else 0
    f_urg  = 1 if 'U' in str(flags) else 0

    return {
        'timestamp':  float(pkt.time),
        'src_ip':     src_ip,
        'dst_ip':     dst_ip,
        'src_port':   sport,
        'dst_port':   dport,
        'pkt_len':    len(pkt),
        'payload_len': payload_len,
        'f_syn': f_syn, 'f_fin': f_fin, 'f_rst': f_rst,
        'f_ack': f_ack, 'f_psh': f_psh, 'f_urg': f_urg,
    }


def build_flows(packets):
    """
    Group packets into bidirectional TCP flows.
    Returns: dict keyed by (src_ip, dst_ip, sport, dport) → list of packet dicts.
    """
    flows_raw = {}   # forward direction
    flows_rev = {}   # reverse direction

    for pkt_dict in packets:
        if pkt_dict is None:
            continue

        # Forward key
        fwd_key = (pkt_dict['src_ip'], pkt_dict['dst_ip'],
                   pkt_dict['src_port'], pkt_dict['dst_port'])
        # Reverse key
        rev_key = (pkt_dict['dst_ip'], pkt_dict['src_ip'],
                   pkt_dict['dst_port'], pkt_dict['src_port'])

        if rev_key in flows_raw:
            flows_raw[rev_key].append(pkt_dict)
        else:
            flows_raw[fwd_key] = flows_raw.get(fwd_key, []) + [pkt_dict]

    return flows_raw


def extract_flow_features(flow_key, pkt_list, label=0, scenario=""):
    """Compute 67 CICFlowMeter-compatible features from a list of packets."""
    if len(pkt_list) < 2:
        return None

    pkt_list = sorted(pkt_list, key=lambda p: p['timestamp'])

    # Split into forward (client→server) and backward (server→client)
    fwd_key = flow_key
    fwd_pkts = [p for p in pkt_list
                if p['src_ip'] == fwd_key[0] and p['src_port'] == fwd_key[2]]
    bwd_pkts = [p for p in pkt_list
                if p['src_ip'] == fwd_key[1] and p['src_port'] == fwd_key[3]]

    timestamps = [p['timestamp'] for p in pkt_list]

    # Basic counts
    n_fwd  = len(fwd_pkts)
    n_bwd  = len(bwd_pkts)
    n_total = n_fwd + n_bwd

    # Payload lengths
    fwd_payloads = [p['payload_len'] for p in fwd_pkts]
    bwd_payloads = [p['payload_len'] for p in bwd_pkts]
    fwd_lens     = [p['pkt_len'] for p in fwd_pkts]
    bwd_lens     = [p['pkt_len'] for p in bwd_pkts]

    total_fwd_bytes = sum(fwd_lens)
    total_bwd_bytes = sum(bwd_lens)

    # Duration (microseconds for CICIDS2017 compatibility)
    duration = (max(timestamps) - min(timestamps)) * 1_000_000
    duration = max(duration, 1.0)

    # IAT (Inter-Arrival Times) in microseconds
    iats = np.diff(timestamps) * 1_000_000
    fwd_iats = np.diff([p['timestamp'] for p in fwd_pkts]) * 1_000_000 if n_fwd > 1 else np.array([0.0])
    bwd_iats = np.diff([p['timestamp'] for p in bwd_pkts]) * 1_000_000 if n_bwd > 1 else np.array([0.0])

    # TCP flags
    n_syn = sum(p['f_syn'] for p in pkt_list)
    n_fin = sum(p['f_fin'] for p in pkt_list)
    n_rst = sum(p['f_rst'] for p in pkt_list)
    n_ack = sum(p['f_ack'] for p in pkt_list)
    n_psh = sum(p['f_psh'] for p in pkt_list)
    n_urg = sum(p['f_urg'] for p in pkt_list)

    # PSH flag per direction
    n_fwd_psh = sum(p['f_psh'] for p in fwd_pkts)
    n_bwd_psh = sum(p['f_psh'] for p in bwd_pkts)
    n_fwd_urg = sum(p['f_urg'] for p in fwd_pkts)
    n_bwd_urg = sum(p['f_urg'] for p in bwd_pkts)

    # Burst detection
    burst_count = int(np.sum(iats < 100_000))  # inter-arrival < 100ms
    burst_ratio = burst_count / max(len(iats), 1)

    # Ratios
    down_up_ratio = total_bwd_bytes / max(total_fwd_bytes, 1)
    upload_ratio  = total_fwd_bytes / max(total_bwd_bytes, 1)

    # Packet length stats (computed first, used inside dict literal)
    all_lens = fwd_lens + bwd_lens

    rec = {
        # === Flow basics ===
        'Flow Duration':                  duration,
        'Total Fwd Packets':              n_fwd,
        'Total Backward Packets':         n_bwd,
        'Total Length of Fwd Packets':    total_fwd_bytes,
        'Total Length of Bwd Packets':    total_bwd_bytes,

        # === Packet length stats ===
        'Fwd Packet Length Max':  max(fwd_lens) if fwd_lens else 0,
        'Fwd Packet Length Min':  min(fwd_lens) if fwd_lens else 0,
        'Fwd Packet Length Mean': np.mean(fwd_lens) if fwd_lens else 0,
        'Fwd Packet Length Std':  np.std(fwd_lens) if len(fwd_lens) > 1 else 0,
        'Bwd Packet Length Max':  max(bwd_lens) if bwd_lens else 0,
        'Bwd Packet Length Min':  min(bwd_lens) if bwd_lens else 0,
        'Bwd Packet Length Mean': np.mean(bwd_lens) if bwd_lens else 0,
        'Bwd Packet Length Std':  np.std(bwd_lens) if len(bwd_lens) > 1 else 0,

        # === Throughput ===
        'Flow Bytes/s':   (total_fwd_bytes + total_bwd_bytes) / (duration / 1_000_000),
        'Flow Packets/s': n_total / (duration / 1_000_000),

        # === IAT ===
        'Flow IAT Mean': np.mean(iats) if len(iats) > 0 else 0,
        'Flow IAT Std':  np.std(iats)  if len(iats) > 1  else 0,
        'Flow IAT Max':  np.max(iats)  if len(iats) > 0 else 0,
        'Flow IAT Min':  np.min(iats)  if len(iats) > 0 else 0,

        # === Forward IAT ===
        'Fwd IAT Total': np.sum(fwd_iats),
        'Fwd IAT Mean': np.mean(fwd_iats) if len(fwd_iats) > 0 else 0,
        'Fwd IAT Std':  np.std(fwd_iats)  if len(fwd_iats) > 1  else 0,
        'Fwd IAT Max':  np.max(fwd_iats)  if len(fwd_iats) > 0 else 0,
        'Fwd IAT Min':  np.min(fwd_iats)  if len(fwd_iats) > 0 else 0,

        # === Backward IAT ===
        'Bwd IAT Total': np.sum(bwd_iats),
        'Bwd IAT Mean': np.mean(bwd_iats) if len(bwd_iats) > 0 else 0,
        'Bwd IAT Std':  np.std(bwd_iats)  if len(bwd_iats) > 1  else 0,
        'Bwd IAT Max':  np.max(bwd_iats)  if len(bwd_iats) > 0 else 0,
        'Bwd IAT Min':  np.min(bwd_iats)  if len(bwd_iats) > 0 else 0,

        # === TCP flags ===
        'Fwd PSH Flags': n_fwd_psh,
        'Bwd PSH Flags': n_bwd_psh,
        'Fwd URG Flags': n_fwd_urg,
        'Bwd URG Flags': n_bwd_urg,
        'FIN Flag Count': n_fin,
        'SYN Flag Count': n_syn,
        'RST Flag Count': n_rst,
        'ACK Flag Count': n_ack,
        'PSH Flag Count': n_psh,
        'URG Flag Count': n_urg,
        'CWE Flag Count': 0,
        'ECE Flag Count': 0,

        # === Rates ===
        'Fwd Packets/s': n_fwd / (duration / 1_000_000),
        'Bwd Packets/s': n_bwd / (duration / 1_000_000),

        # === Packet length global ===
        all_lens = fwd_lens + bwd_lens
        'Min Packet Length': min(all_lens) if all_lens else 0,
        'Max Packet Length': max(all_lens) if all_lens else 0,
        'Packet Length Mean': np.mean(all_lens) if all_lens else 0,
        'Packet Length Std':  np.std(all_lens)  if len(all_lens) > 1 else 0,
        'Packet Length Variance': np.var(all_lens) if len(all_lens) > 1 else 0,

        # === Ratios ===
        'Down/Up Ratio': down_up_ratio,
        'Average Packet Size': np.mean(all_lens) if all_lens else 0,
        'Avg Fwd Segment Size': np.mean(fwd_payloads) if fwd_payloads else 0,
        'Avg Bwd Segment Size': np.mean(bwd_payloads) if bwd_payloads else 0,

        # === Header lengths (fixed 40 = IP20 + TCP20) ===
        'Fwd Header Length': 40 * n_fwd,
        'Bwd Header Length': 40 * n_bwd,
        'Fwd Header Length.1': 0,  # CICFlowMeter artifact
        'min_seg_size_forward': 0,

        # === Subflow ===
        'Subflow Fwd Packets': n_fwd,
        'Subflow Fwd Bytes':    total_fwd_bytes,
        'Subflow Bwd Packets': n_bwd,
        'Subflow Bwd Bytes':    total_bwd_bytes,

        # === Window sizes ===
        'Init_Win_bytes_forward': fwd_lens[0]  if fwd_lens else 0,
        'Init_Win_bytes_backward': bwd_lens[0] if bwd_lens else 0,

        # === Active/idle (simple proxy: IAT-based) ===
        'Active Mean': np.mean(fwd_iats) if len(fwd_iats) > 0 else 0,
        'Active Std':  np.std(fwd_iats)  if len(fwd_iats) > 1 else 0,
        'Active Max':  np.max(fwd_iats)  if len(fwd_iats) > 0 else 0,
        'Active Min':  np.min(fwd_iats)  if len(fwd_iats) > 0 else 0,
        'Idle Mean':   np.mean(bwd_iats) if len(bwd_iats) > 0 else 0,
        'Idle Std':    np.std(bwd_iats)  if len(bwd_iats) > 1 else 0,
        'Idle Max':    np.max(bwd_iats)  if len(bwd_iats) > 0 else 0,
        'Idle Min':    np.min(bwd_iats)  if len(bwd_iats) > 0 else 0,

        # === Custom exfil features ===
        'upload_download_ratio':  upload_ratio,
        'burst_count':            burst_count,
        'unusual_port_ratio':     0.0,   # lab traffic only
        'requests_per_second':    n_total / (duration / 1_000_000),
        'inter_request_time_std': np.std(iats) if len(iats) > 1 else 0,
        'act_data_pkt_fwd':       sum(1 for p in fwd_pkts if p['payload_len'] > 0),

        # === Metadata ===
        'Label':    label,
        'Scenario': scenario,
        'Flow Key': f"{flow_key[0]}:{flow_key[2]}→{flow_key[1]}:{flow_key[3]}",
        'n_packets': n_total,
        'src_port': flow_key[2],
        'dst_port': flow_key[3],
    }

    return rec


def process_pcap(pcap_path: str, label: int = 0, scenario: str = "") -> pd.DataFrame:
    """Process a single PCAP file → DataFrame of flow features."""
    try:
        print(f"  Processing: {pcap_path}")
        packets_raw = rdpcap(str(pcap_path))
        print(f"  Packets: {len(packets_raw)}")

        pkt_dicts = [packet_to_flow_dict(p) for p in packets_raw]
        pkt_dicts = [p for p in pkt_dicts if p is not None]
        print(f"  TCP/IP packets: {len(pkt_dicts)}")

        flows = build_flows(pkt_dicts)
        print(f"  Flows: {len(flows)}")

        records = []
        for flow_key, pkt_list in flows.items():
            rec = extract_flow_features(flow_key, pkt_list, label, scenario)
            if rec is not None:
                records.append(rec)

        if records:
            df = pd.DataFrame(records)
            print(f"  Flows extracted: {len(df)}")
            return df
        return pd.DataFrame()
    except Exception as e:
        print(f"  ERROR processing {pcap_path}: {e}")
        import traceback; traceback.print_exc()
        return pd.DataFrame()


def process_scenarios(scenarios_dir: str, output_csv: str):
    """
    Merge all scenarios → single CSV with ground-truth labels.

    Scenario mapping:
      baseline      → Label 0 (normal)
      burst_exfil   → Label 1 (exfil)
      slow_exfil    → Label 1 (exfil)
      https_exfil   → Label 1 (exfil)
    """
    scenarios = {
        'baseline':    (0, 'Normal traffic'),
        'burst_exfil': (1, 'Burst exfiltration'),
        'slow_exfil':  (1, 'Slow exfiltration'),
        'https_exfil': (1, 'HTTPS metadata exfil'),
    }

    all_dfs = []
    for scenario_name, (label, desc) in scenarios.items():
        scenario_path = Path(scenarios_dir) / scenario_name
        if not scenario_path.exists():
            print(f"  Skipping {scenario_name} (directory not found)")
            continue

        pcap_files = sorted(scenario_path.glob('*.pcap'))
        if not pcap_files:
            print(f"  No PCAP files in {scenario_name}/")
            continue

        print(f"\n  [{scenario_name}] {desc} (label={label})")
        for pcap_file in pcap_files:
            df = process_pcap(str(pcap_file), label=label, scenario=scenario_name)
            if not df.empty:
                all_dfs.append(df)

    if not all_dfs:
        print("No data extracted!")
        return None

    final_df = pd.concat(all_dfs, ignore_index=True)

    # Add destination port as feature (CICIDS2017 has it)
    if 'Destination Port' not in final_df.columns and 'dst_port' in final_df.columns:
        final_df['Destination Port'] = final_df['dst_port']

    # Clip infinities
    numeric_cols = final_df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        final_df[col] = final_df[col].replace([np.inf, -np.inf], np.nan).fillna(0)

    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    final_df.to_csv(output_csv, index=False)

    print(f"\n{'='*60}")
    print(f"Total flows: {len(final_df)}")
    print(f"Label distribution:\n{final_df['Label'].value_counts()}")
    print(f"Scenario distribution:\n{final_df['Scenario'].value_counts()}")
    print(f"Saved: {output_csv}")

    return final_df


if __name__ == '__main__':
    scenarios_dir = 'data/self_captured/scenarios'
    output_csv    = 'data/self_captured/self_captured_features.csv'

    print(f"\n{'='*60}")
    print("PCAP → Flow Feature Extraction")
    print(f"{'='*60}")
    print(f"Scenarios dir: {scenarios_dir}")
    print(f"Output CSV:    {output_csv}")

    df = process_scenarios(scenarios_dir, output_csv)

    if df is not None:
        print(f"\nFeature columns ({len(df.columns)} total):")
        print(df.dtypes.value_counts())
