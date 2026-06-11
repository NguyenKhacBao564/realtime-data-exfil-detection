#!/usr/bin/env bash
# scripts/run_live_lab.sh — Run the detection pipeline in live mode.
#
# Usage:
#   sudo ./run_live_lab.sh [iface] [--online-monitor]
#
# Examples:
#   sudo ./run_live_lab.sh eth0                 # basic live capture
#   sudo ./run_live_lab.sh eth0 --online-monitor  # with online anomaly detection
#   sudo ./run_live_lab.sh                      # auto-detect interface

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Parse arguments
IFACE=""
ENABLE_ONLINE=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --online-monitor)
            ENABLE_ONLINE="--enable-online-monitor"
            shift
            ;;
        -*)
            echo "Unknown option: $1"
            exit 1
            ;;
        *)
            IFACE="$1"
            shift
            ;;
    esac
done

# Auto-detect interface
if [[ -z "$IFACE" ]]; then
    echo "=== Available interfaces ==="
    ip -br addr show 2>/dev/null | grep -v "^lo\|^docker\|^br-\|^veth" | awk '{print $1, $3}' || true
    echo ""
    if command -v ifconfig &>/dev/null; then
        echo "Interfaces:"
        ifconfig -a 2>/dev/null | grep -E "^[a-z]" | awk '{print " ", $1}' || true
    fi
    echo ""
    read -rp "Enter interface name (e.g. eth0, en0): " IFACE
fi

if [[ -z "$IFACE" ]]; then
    echo "ERROR: No interface specified."
    exit 1
fi

# Validate Python env
if ! python3 -c "import scapy" 2>/dev/null; then
    echo "ERROR: scapy not installed. Run: pip install scapy"
    exit 1
fi

echo "========================================"
echo "  Live Detection Lab"
echo "========================================"
echo "  Interface:       $IFACE"
echo "  Online Monitor:  ${ENABLE_ONLINE:-disabled}"
echo "  Project Root:    $PROJECT_ROOT"
echo "========================================"
echo ""

# Check sudo
if ! sudo -n true 2>/dev/null; then
    echo "NOTE: sudo access is needed for live packet capture."
fi

# Run the pipeline
exec sudo python3 -u src/pipeline.py \
    --live \
    --iface "$IFACE" \
    ${ENABLE_ONLINE} \
    --debug
