#!/usr/bin/env bash
# scripts/run_offline_replay.sh — Replay a PCAP file through the detection pipeline.
#
# Usage:
#   ./run_offline_replay.sh [pcap_file] [--online-monitor]
#
# Examples:
#   ./run_offline_replay.sh lab/captures/lab_20250601_120000.pcap
#   ./run_offline_replay.sh data/raw/Friday-WorkingHours.pcap --online-monitor
#   ./run_offline_replay.sh    # shows available PCAP files

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Parse arguments
PCAP_FILE=""
ENABLE_ONLINE=""
WINDOW_SIZE=""
BURST_THRESHOLD=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --online-monitor)
            ENABLE_ONLINE="--enable-online-monitor"
            shift
            ;;
        --window-size)
            WINDOW_SIZE="--window-size $2"
            shift 2
            ;;
        --burst-threshold)
            BURST_THRESHOLD="--burst-threshold $2"
            shift 2
            ;;
        -*)
            echo "Unknown option: $1"
            exit 1
            ;;
        *)
            PCAP_FILE="$1"
            shift
            ;;
    esac
done

# Prompt for PCAP if not provided
if [[ -z "$PCAP_FILE" ]]; then
    echo "=== Available PCAP files ==="
    find "$PROJECT_ROOT" -name "*.pcap" -type f 2>/dev/null | sort | head -20
    echo ""
    echo "=== Recent lab captures ==="
    ls -lh "$PROJECT_ROOT/lab/captures/"*.pcap 2>/dev/null | tail -5 || true
    echo ""
    read -rp "Enter PCAP file path: " PCAP_FILE
fi

if [[ -z "$PCAP_FILE" ]]; then
    echo "ERROR: No PCAP file specified."
    exit 1
fi

# Resolve path
if [[ ! -f "$PCAP_FILE" ]]; then
    echo "ERROR: File not found: $PCAP_FILE"
    exit 1
fi

PCAP_ABS="$(realpath "$PCAP_FILE")"
FILE_SIZE=$(du -h "$PCAP_ABS" | cut -f1)

echo "========================================"
echo "  Offline PCAP Replay"
echo "========================================"
echo "  PCAP file:      $PCAP_ABS"
echo "  File size:      $FILE_SIZE"
echo "  Online Monitor: ${ENABLE_ONLINE:-disabled}"
echo "========================================"
echo ""

exec python3 -u src/pipeline.py \
    --offline \
    --pcap "$PCAP_ABS" \
    ${ENABLE_ONLINE} \
    ${WINDOW_SIZE:-} \
    ${BURST_THRESHOLD:-} \
    --debug
