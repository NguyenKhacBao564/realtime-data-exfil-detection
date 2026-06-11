#!/usr/bin/env bash
# scripts/collect_demo_evidence.sh — Collect non-sensitive demo metadata for documentation.
#
# Collects: git hash, Python version, pip packages, CLI help, docker config, PCAP list.
# Does NOT collect: payload contents, PCAP packet contents, secrets, logs.
#
# Usage:
#   ./scripts/collect_demo_evidence.sh
#   ./scripts/collect_demo_evidence.sh docs/demo_evidence.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT="${1:-${PROJECT_ROOT}/docs/demo_evidence.md}"

cd "$PROJECT_ROOT"

# Remove old evidence if exists
> "$OUTPUT"

append() {
    tee -a "$OUTPUT"
}

echo "Collecting demo evidence to: $OUTPUT"

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
{
    cat <<'HEADER'
# docs/demo_evidence.md

# Demo Evidence — Auto-Generated

> **WARNING:** This file is auto-generated. Do not commit sensitive information.
> Review contents before sharing. PCAP file paths and log snippets below are safe
> (synthetic lab traffic only).

---

## Git Information

HEADER
} | append

git rev-parse HEAD 2>/dev/null | append || echo "(not a git repo)" | append
echo "" | append
git status --short 2>/dev/null | append || echo "(not a git repo)" | append

# Python version
{
    echo ""
    echo "## Python Environment"
    echo ""
    echo '```'
    echo '$ python3 --version'
} | append
python3 --version 2>&1 | append
echo '```' | append

{
    echo ""
    echo '$ pip list --format=freeze 2>/dev/null | head -20'
} | append
pip list --format=freeze 2>/dev/null | grep -E "^(scapy|pandas|numpy|scikit-learn|tensorflow|keras|joblib|tqdm|requests|pytest)" | append || echo "(pip not available)" | append

# Pipeline CLI help
{
    echo ""
    echo "## Pipeline CLI Help"
    echo ""
    echo '```'
    echo '$ python3 src/pipeline.py --help'
} | append
python3 src/pipeline.py --help 2>&1 | head -50 | append
echo '```' | append

# Traffic generator help
{
    echo ""
    echo "## Traffic Generator CLI Help"
    echo ""
    echo '```'
    echo '$ python3 lab/victim/generate_http_traffic.py --help'
} | append
python3 lab/victim/generate_http_traffic.py --help 2>&1 | append
echo '```' | append

# Demo server help
{
    echo ""
    echo "## Demo Server CLI Help"
    echo ""
    echo '```'
    echo '$ python3 lab/server/receiver.py --help'
} | append
python3 lab/server/receiver.py --help 2>&1 | append
echo '```' | append

# Docker Compose config
{
    echo ""
    echo "## Docker Compose Configuration"
    echo ""
    echo "_Validated: $(date '+%Y-%m-%d %H:%M:%S')_"
    echo ""
    echo '```yaml'
    echo '$ docker compose -f lab/docker-compose.yml config'
} | append
if docker compose -f lab/docker-compose.yml config >/dev/null 2>&1; then
    docker compose -f lab/docker-compose.yml config 2>&1 | append
    echo "Docker Compose config: VALID" | append
else
    echo "Docker Compose config: UNAVAILABLE (Docker not running or not installed)" | append
fi
echo '```' | append

# PCAP files
{
    echo ""
    echo "## Lab Captures"
    echo ""
    echo "_PCAP files (metadata only — no packet contents included)_"
    echo ""
} | append
if [[ -d "$PROJECT_ROOT/lab/captures" ]]; then
    {
        echo '$ ls -lh lab/captures/'
    } | append
    ls -lh "$PROJECT_ROOT/lab/captures/"*.pcap 2>/dev/null | append || echo "(no PCAP files found)" | append
else
    echo "(lab/captures/ directory does not exist yet)" | append
fi

# Alert log tail
{
    echo ""
    echo "## Recent Alerts (if any)"
    echo ""
    echo "_Last 20 alert lines from exfil_detection.log (synthetic only)_"
    echo ""
    echo '```'
    echo '$ tail -20 exfil_detection.log 2>/dev/null'
} | append
if [[ -f "$PROJECT_ROOT/exfil_detection.log" ]]; then
    tail -20 "$PROJECT_ROOT/exfil_detection.log" 2>/dev/null | append || echo "(empty or unreadable)" | append
else
    echo "(exfil_detection.log not found — run pipeline first)" | append
fi
echo '```' | append

# Test summary
{
    echo ""
    echo "## Test Summary"
    echo ""
    echo '```'
    echo '$ pytest tests/unit/test_online_anomaly_monitor.py tests/integration/test_online_inference_integration.py -v --tb=no'
} | append
pytest tests/unit/test_online_anomaly_monitor.py tests/integration/test_online_inference_integration.py -v --tb=no 2>&1 | tail -20 | append || echo "(pytest not available)" | append
echo '```' | append

# Footer
{
    echo ""
    echo "---"
    echo "*Generated: $(date '+%Y-%m-%d %H:%M:%S')*"
    echo "*Source: scripts/collect_demo_evidence.sh*"
} | append

echo ""
echo "Done. Evidence written to: $OUTPUT"
echo "Review before sharing. Remove any sensitive content."
