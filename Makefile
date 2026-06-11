# Makefile — HTTP Data Exfiltration Detection Lab
#
# Convenience task runner. All tasks are wrappers around existing scripts.
# The scripts themselves are the source of truth; this file is optional.
#
# Usage:
#   make help              Show all targets
#   make test              Run unit + integration tests
#   make compile           Syntax check all Python files
#   make lab-up            Start the Docker lab
#   make lab-down          Stop the Docker lab
#   make lab-normal        Run normal traffic for N seconds
#   make lab-exfil         Run exfil traffic for N seconds
#   make lab-slow-drip     Run slow-drip traffic for N seconds
#   make live-demo          Run live detection (requires sudo)
#   make offline-replay    Replay a PCAP file
#
# Examples:
#   make lab-up
#   DURATION=120 make lab-normal
#   make lab-exfil
#   sudo DURATION=60 make live-demo
#   PCAP=lab/captures/demo.pcap make offline-replay
#   make test

.PHONY: help test compile lab-up lab-down lab-normal lab-exfil lab-slow-drip live-demo offline-replay lab-generate

# Default durations (seconds)
DURATION ?= 60
PCAP ?= lab/captures/demo.pcap

help:
	@echo "HTTP Data Exfiltration Detection — Lab Targets"
	@echo ""
	@echo "  Setup:"
	@echo "    make compile          Syntax-check all Python files"
	@echo "    make test             Run unit + integration tests"
	@echo ""
	@echo "  Docker Lab:"
	@echo "    make lab-up           Start lab (docker-compose up -d)"
	@echo "    make lab-down         Stop lab (docker-compose down)"
	@echo "    make lab-logs         Follow exfil-server logs"
	@echo ""
	@echo "  Traffic Generation (run while lab is up):"
	@echo "    make lab-normal       Normal browsing traffic (DURATION=$(DURATION)s)"
	@echo "    make lab-exfil        Simulated exfiltration burst (DURATION=$(DURATION)s)"
	@echo "    make lab-slow-drip    Slow-drip anomaly (DURATION=$(DURATION)s)"
	@echo ""
	@echo "  Detection:"
	@echo "    sudo make live-demo   Live detection (INTERFACE=eth0, requires sudo)"
	@echo "    make offline-replay   Replay PCAP (PCAP=$(PCAP))"
	@echo ""
	@echo "  Variables:"
	@echo "    DURATION=<secs>       Override traffic duration (default: 60)"
	@echo "    PCAP=<file>           PCAP file for offline replay (default: lab/captures/demo.pcap)"
	@echo "    INTERFACE=<iface>     Network interface for live capture (default: eth0)"
	@echo ""

# ---------------------------------------------------------------------------
# Quality assurance
# ---------------------------------------------------------------------------

test:
	@echo "Running unit + integration tests..."
	pytest tests/unit/test_online_anomaly_monitor.py \
	       tests/integration/test_online_inference_integration.py \
	       -v --tb=short

compile:
	@echo "Checking Python syntax..."
	python3 -m compileall src lab scripts tests
	@echo "OK — no syntax errors"

# ---------------------------------------------------------------------------
# Docker lab lifecycle
# ---------------------------------------------------------------------------

lab-up:
	@echo "Starting Docker lab..."
	cd lab && docker-compose up -d
	@echo "Lab started. Run 'make lab-logs' to follow server logs."
	@echo "Then: make lab-normal  (generate baseline traffic)"
	@echo "Then: make lab-exfil   (simulate exfiltration)"

lab-down:
	@echo "Stopping Docker lab..."
	cd lab && docker-compose down

lab-logs:
	cd lab && docker-compose logs -f exfil-server

# ---------------------------------------------------------------------------
# Traffic generation (run in separate terminals)
# ---------------------------------------------------------------------------

lab-generate:
	@echo "ERROR: use lab-normal, lab-exfil, or lab-slow-drip"
	@false

lab-normal:
	@echo "Generating NORMAL traffic for $(DURATION)s..."
	@echo "Run 'make lab-logs' in another terminal to watch server logs."
	cd lab && docker-compose run --rm victim-client \
		python3 /generate.py --mode normal \
		--server http://exfil-server:8000 \
		--duration $(DURATION)

lab-exfil:
	@echo "Generating EXFILTRATION traffic for $(DURATION)s..."
	@echo "Run 'make lab-logs' in another terminal to watch server logs."
	cd lab && docker-compose run --rm victim-client \
		python3 /generate.py --mode exfil \
		--server http://exfil-server:8000 \
		--duration $(DURATION)

lab-slow-drip:
	@echo "Generating SLOW-DRIP traffic for $(DURATION)s..."
	@echo "Run 'make lab-logs' in another terminal to watch server logs."
	cd lab && docker-compose run --rm victim-client \
		python3 /generate.py --mode slow-drip \
		--server http://exfil-server:8000 \
		--duration $(DURATION)

# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

# Live detection inside the monitor container
# Requires INTERFACE env var (default eth0)
live-demo:
	@echo "Running live detection on interface $(INTERFACE)..."
	cd lab && docker-compose exec monitor-detector \
		python3 -u src/pipeline.py \
		--live \
		--iface $(INTERFACE) \
		--enable-online-monitor \
		--debug

# Live detection from host (requires sudo + scapy installed on host)
live-demo-host:
	@echo "Running live detection on host (requires sudo)..."
	@echo "Interface: $(INTERFACE)"
	@if [ -f "$(PCAP)" ]; then echo "PCAP: $(PCAP)"; else echo "PCAP not found: $(PCAP)"; fi
	@echo "Starting pipeline..."
	cd /Users/nguyen_bao/Projects/AIproject/AI_Project/Exfiltration && \
		sudo python3 -u src/pipeline.py \
		--live \
		--iface $(INTERFACE) \
		--enable-online-monitor \
		--debug

# Replay a captured PCAP file through the pipeline
offline-replay:
	@if [ ! -f "$(PCAP)" ]; then \
		echo "ERROR: PCAP file not found: $(PCAP)"; \
		echo "Capture first: sudo ./scripts/capture_lab_pcap.sh eth0 60"; \
		exit 1; \
	fi
	@echo "Replaying $(PCAP)..."
	@echo "Files in lab/captures/:"
	@ls -lh lab/captures/*.pcap 2>/dev/null || echo "  (none found)"
	cd /Users/nguyen_bao/Projects/AIproject/AI_Project/Exfiltration && \
		python3 -u src/pipeline.py \
		--offline \
		--pcap $(PCAP) \
		--enable-online-monitor \
		--debug

# Capture traffic to PCAP
capture:
	@echo "Capturing traffic on $(INTERFACE) for $(DURATION)s..."
	@sudo ./scripts/capture_lab_pcap.sh $(INTERFACE) $(DURATION) lab/captures/demo.pcap

.DEFAULT_GOAL := help
