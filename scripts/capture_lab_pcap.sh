#!/usr/bin/env bash
# scripts/capture_lab_pcap.sh — Capture network traffic to PCAP for lab replay.
#
# Usage:
#   sudo ./capture_lab_pcap.sh [iface] [duration] [output_file]
#
# Examples:
#   sudo ./capture_lab_pcap.sh                    # auto-detect iface, 60s, default output
#   sudo ./capture_lab_pcap.sh eth0 120           # capture eth0 for 120s
#   sudo ./capture_lab_pcap.sh any 60 custom.pcap # custom file
#
# NOTE: Requires sudo for raw packet capture.
# Captures ALL TCP/UDP traffic on the interface (no payload filtering applied).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CAPTURES_DIR="${PROJECT_ROOT}/lab/captures"
mkdir -p "$CAPTURES_DIR"

# Defaults
IFACE="${1:-}"
DURATION="${2:-60}"
OUTPUT="${3:-${CAPTURES_DIR}/lab_$(date +%Y%m%d_%H%M%S).pcap}"

# Auto-detect interface if not provided
if [[ -z "$IFACE" ]]; then
    echo "=== Available network interfaces ==="
    # Try ip first, fallback to ifconfig
    if command -v ip &>/dev/null; then
        ip -br addr show | grep -v "^lo\|^docker\|^br-\|^veth" || true
    fi
    if command -v ifconfig &>/dev/null; then
        ifconfig -a | grep -E "^[a-z]" | awk '{print $1}' || true
    fi
    echo ""
    echo "Usage: $0 [iface] [duration] [output_file]"
    echo "Example: $0 eth0 60"
    echo ""
    read -rp "Enter interface name: " IFACE
fi

if [[ -z "$IFACE" ]]; then
    echo "ERROR: No interface specified."
    exit 1
fi

echo "========================================"
echo "  PCAP Capture Tool"
echo "========================================"
echo "  Interface:  $IFACE"
echo "  Duration:    ${DURATION}s"
echo "  Output:      $OUTPUT"
echo "========================================"
echo ""

# Check for tcpdump
if ! command -v tcpdump &>/dev/null; then
    echo "ERROR: tcpdump not found. Install with: sudo apt install tcpdump"
    exit 1
fi

# Check for sudo
if ! sudo -n true 2>/dev/null; then
    echo "NOTE: sudo password may be requested for packet capture."
fi

# Validate interface exists
if ! ip link show "$IFACE" &>/dev/null && ! ifconfig "$IFACE" &>/dev/null; then
    echo "WARNING: Interface '$IFACE' not found. Available interfaces:"
    ip -br addr show 2>/dev/null | awk '{print $1}' || true
fi

# Start capture
echo "[$(date '+%H:%M:%S')] Starting capture on $IFACE..."
sudo tcpdump -i "$IFACE" \
    -s 65535 \
    -w "$OUTPUT" \
    -W 1 \
    -G "$DURATION" \
    -Z "$(whoami)" \
    -v \
    2>&1 | while IFS= read -r line; do
        echo "[tcpdump] $line"
    done &

TCPID=$!
sleep 1

echo "[$(date '+%H:%M:%S')] Capturing for ${DURATION}s (PID=$TCPID)..."
echo "[$(date '+%H:%M:%S')] Output: $OUTPUT"
echo "Press Ctrl+C to stop early."

# Wait with progress
for i in $(seq 1 "$DURATION"); do
    sleep 1
    printf "\r[%3d/%3d] Capturing... " "$i" "$DURATION"
done
echo ""

wait $TCPID 2>/dev/null || true

# Report
if [[ -f "$OUTPUT" ]]; then
    SIZE=$(du -h "$OUTPUT" | cut -f1)
    PKTS=$(sudo tcpdump -r "$OUTPUT" -c 0 2>/dev/null | tail -1 || echo "unknown")
    echo ""
    echo "=== Capture Complete ==="
    echo "  File: $OUTPUT"
    echo "  Size: $SIZE"
    echo "  Packets: $PKTS"
    echo ""
    echo "To replay offline:"
    echo "  python src/pipeline.py --offline --pcap $OUTPUT --enable-online-monitor"
else
    echo "ERROR: Capture file not created."
    exit 1
fi
