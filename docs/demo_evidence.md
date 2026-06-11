# docs/demo_evidence.md

# Demo Evidence — Auto-Generated

> **WARNING:** This file is auto-generated. Do not commit sensitive information.
> Review contents before sharing. PCAP file paths and log snippets below are safe
> (synthetic lab traffic only).

---

## Git Information

659ad2b0ae430bfd5210f3873463a18897ea8f05

 M .gitignore
 M README.md
 M src/inference/alert_logger.py
 M src/inference/model_inference.py
 M src/pipeline.py
 M src/train/extract_pcap_features.py
 M src/utils/config.py
 M topic.md
?? .env.example
?? Makefile
?? docs/DEMO_SCRIPT.md
?? docs/EVALUATION_PLAN.md
?? docs/IMPLEMENTATION_SUMMARY.md
?? docs/ONLINE_ANOMALY_DESIGN.md
?? docs/TEACHER_REQUIREMENT_MAPPING.md
?? docs/VM_DOCKER_LAB_GUIDE.md
?? docs/checkin_thay.docx
?? docs/demo_evidence.md
?? docs/write_checkin.py
?? exfil_detection.log.bak
?? lab/
?? scripts/
?? src/inference/online_anomaly_monitor.py
?? tests/

## Python Environment

```
$ python3 --version
Python 3.13.12
```

$ pip list --format=freeze 2>/dev/null | head -20
joblib==1.5.3
numpy==2.4.4
pandas==3.0.2
pytest==9.0.3
requests==2.32.5
scikit-learn==1.8.0
tqdm==4.67.3

## Pipeline CLI Help

```
$ python3 src/pipeline.py --help
usage: pipeline.py [-h] [--offline | --live] [--pcap PCAP] [--iface IFACE]
                   [--capture-host CAPTURE_HOST] [--model MODEL]
                   [--scaler SCALER] [--window-size WINDOW_SIZE]
                   [--burst-threshold BURST_THRESHOLD]
                   [--enable-online-monitor]
                   [--online-threshold ONLINE_THRESHOLD]
                   [--online-warmup-windows ONLINE_WARMUP_WINDOWS] [--debug]

HTTP Exfiltration Detection Pipeline (offline-trained models + burst rules + online adaptive monitor)

options:
  -h, --help            show this help message and exit
  --offline             Run in offline mode (read PCAP file)
  --live                Run in live mode (sniff network interface)
  --pcap PCAP           Path to PCAP file (offline mode)
  --iface IFACE         Network interface name (live mode)
  --capture-host CAPTURE_HOST
                        Only capture packets where src/dst IP matches this
                        host
  --model MODEL         Path to model file (.pkl or .h5)
  --scaler SCALER       Path to scaler file (.pkl)
  --window-size WINDOW_SIZE
                        Aggregation window size in seconds
  --burst-threshold BURST_THRESHOLD
                        Alert threshold for burst_exfil_score
  --enable-online-monitor
                        Enable the online anomaly monitor (detects unknown/new
                        patterns)
  --online-threshold ONLINE_THRESHOLD
                        Alert threshold for online anomaly score (0-1)
                        [default: 0.5]
  --online-warmup-windows ONLINE_WARMUP_WINDOWS
                        Normal windows needed before online scoring starts
                        [default: 10]
  --debug               Enable DEBUG logging
```

## Traffic Generator CLI Help

```
$ python3 lab/victim/generate_http_traffic.py --help
usage: generate_http_traffic.py [-h] [--mode {normal,exfil,slow-drip}]
                                [--server SERVER] [--duration DURATION]
                                [--session-id SESSION_ID]

Synthetic HTTP traffic generator for lab demo. ALL payloads are dummy bytes —
no real data.

options:
  -h, --help            show this help message and exit
  --mode {normal,exfil,slow-drip}
                        Traffic mode (normal=human-like, exfil=burst upload,
                        slow-drip=regular small uploads)
  --server SERVER       Base URL of the exfil server [default: http://exfil-
                        server:8000]
  --duration DURATION   Duration in seconds [default: 60]
  --session-id SESSION_ID
                        Session ID (auto-generated if not provided)
```

## Demo Server CLI Help

```
$ python3 lab/server/receiver.py --help
usage: receiver.py [-h] [--port PORT] [--bind BIND] [--max-upload MAX_UPLOAD]

Simple HTTP server for exfiltration detection lab demo. Logs METADATA ONLY —
no content stored.

options:
  -h, --help            show this help message and exit
  --port PORT           Port to listen on [default: 8000]
  --bind BIND           Bind address [default: 0.0.0.0]
  --max-upload MAX_UPLOAD
                        Max upload size in bytes [default: 10MB]
```

## Docker Compose Configuration

_Validated: 2026-06-01 10:13:47_

```yaml
$ docker compose -f lab/docker-compose.yml config
name: lab
services:
  exfil-server:
    command:
      - python3
      - -c
      - |2

          import logging, sys
          logging.basicConfig(
              level=logging.INFO,
              format='%(asctime)s [%(levelname)s] %(message)s',
              stream=sys.stdout
          );
          exec(open('/receiver.py').read())
    container_name: exfil-server
    hostname: exfil-server
    healthcheck:
      test:
        - CMD-SHELL
        - python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/browse', timeout=3)"
      timeout: 5s
      interval: 30s
      retries: 3
    image: python:3.11-slim
    networks:
      exfil-lab: null
    ports:
      - mode: ingress
        target: 8000
        published: "8000"
        protocol: tcp
    volumes:
      - type: bind
        source: /Users/nguyen_bao/Projects/AIproject/AI_Project/Exfiltration/lab/server/receiver.py
        target: /receiver.py
        read_only: true
        bind:
          create_host_path: true
  monitor-detector:
    build:
      context: /Users/nguyen_bao/Projects/AIproject/AI_Project
      dockerfile: lab/monitor/Dockerfile
    command:
      - sleep
      - infinity
    container_name: monitor-detector
    environment:
      PYTHONUNBUFFERED: "1"
    hostname: monitor-detector
    networks:
      exfil-lab: null
    volumes:
      - type: bind
        source: /Users/nguyen_bao/Projects/AIproject/AI_Project/src
        target: /app/src
        read_only: true
        bind:
          create_host_path: true
      - type: bind
        source: /Users/nguyen_bao/Projects/AIproject/AI_Project/models
        target: /app/models
        read_only: true
        bind:
          create_host_path: true
      - type: bind
        source: /Users/nguyen_bao/Projects/AIproject/AI_Project/lab/captures
        target: /app/lab/captures
        bind:
          create_host_path: true
  victim-client:
    command:
      - sleep
      - infinity
    container_name: victim-client
    depends_on:
      exfil-server:
        condition: service_healthy
        required: true
    hostname: victim-client
    image: python:3.11-slim
    networks:
      exfil-lab: null
    volumes:
      - type: bind
        source: /Users/nguyen_bao/Projects/AIproject/AI_Project/Exfiltration/lab/victim/generate_http_traffic.py
        target: /generate.py
        read_only: true
        bind:
          create_host_path: true
networks:
  exfil-lab:
    name: lab_exfil-lab
    driver: bridge
    ipam:
      config:
        - subnet: 172.28.0.0/16
Docker Compose config: VALID
```

## Lab Captures

_PCAP files (metadata only — no packet contents included)_

$ ls -lh lab/captures/
(no PCAP files found)

## Recent Alerts (if any)

_Last 20 alert lines from exfil_detection.log (synthetic only)_

```
$ tail -20 exfil_detection.log 2>/dev/null
  Requests:      1523
  Total bytes:   3,503,492  (↑3,496,463 / ↓7,029)
  Upload ratio:  497.43x
  Burst count:   830  (ratio: 1.00)
  Unusual ports: 50.0%
  Destinations: 1
  Session len:  7.3s
  ── Scores ──
  Burst score:   0.800
  Model score:   1.000
  Prediction:    EXFILTRATION
━━━━━━━━━━━━━━━━━━━━━━━━
2026-04-30 23:23:32 WARNING  — Shutdown signal received — stopping pipeline...
2026-04-30 23:23:32 INFO     — [AGGREGATOR] Shutdown — flushing remaining buffers...
2026-04-30 23:23:32 INFO     — [AGGREGATOR] Thread stopped. windows=5 skipped=0 packets=2656
2026-04-30 23:23:33 INFO     — [INFERENCE] Shutdown — draining remaining features...
2026-04-30 23:23:33 INFO     — [INFERENCE] Thread stopped. processed=5 alerts=2
2026-04-30 23:23:33 INFO     — Waiting for threads to finish...
2026-04-30 23:23:33 INFO     — [CAPTURE] Thread stopped. seen=2656 queued=2656 skipped=0
2026-04-30 23:23:33 INFO     — Pipeline stopped gracefully.
```

## Test Summary

```
$ pytest tests/unit/test_online_anomaly_monitor.py tests/integration/test_online_inference_integration.py -v --tb=no
tests/unit/test_online_anomaly_monitor.py::TestOnlineAnomalyMonitor::test_high_deviation_triggers_prediction PASSED [ 54%]
tests/unit/test_online_anomaly_monitor.py::TestOnlineAnomalyMonitor::test_reason_codes_in_result PASSED [ 56%]
tests/unit/test_online_anomaly_monitor.py::TestOnlineAnomalyMonitor::test_multi_ip_isolation PASSED [ 59%]
tests/unit/test_online_anomaly_monitor.py::TestOnlineAnomalyMonitor::test_get_stats PASSED [ 62%]
tests/unit/test_online_anomaly_monitor.py::TestOnlineAnomalyMonitor::test_reset PASSED [ 64%]
tests/unit/test_online_anomaly_monitor.py::TestOnlineAnomalyMonitor::test_reset_ip PASSED [ 67%]
tests/unit/test_online_anomaly_monitor.py::TestOnlineAnomalyMonitor::test_all_runtime_features_accepted PASSED [ 70%]
tests/unit/test_online_anomaly_monitor.py::TestBurstExfilStillWorks::test_burst_exfil_normal PASSED [ 72%]
tests/unit/test_online_anomaly_monitor.py::TestBurstExfilStillWorks::test_burst_exfil_exfil PASSED [ 75%]
tests/unit/test_online_anomaly_monitor.py::TestPipelineImports::test_model_inference_imports PASSED [ 78%]
tests/unit/test_online_anomaly_monitor.py::TestPipelineImports::test_online_monitor_imports PASSED [ 81%]
tests/unit/test_online_anomaly_monitor.py::TestPipelineImports::test_pipeline_imports PASSED [ 83%]
tests/integration/test_online_inference_integration.py::TestOnlineMonitorAlertIntegration::test_format_alert_with_online_fields PASSED [ 86%]
tests/integration/test_online_inference_integration.py::TestOnlineMonitorAlertIntegration::test_format_alert_without_online_fields PASSED [ 89%]
tests/integration/test_online_inference_integration.py::TestOnlineMonitorAlertIntegration::test_full_alert_chain_with_all_triggers PASSED [ 91%]
tests/integration/test_online_inference_integration.py::TestOnlineMonitorInFeatureQueue::test_processes_multiple_windows PASSED [ 94%]
tests/integration/test_online_inference_integration.py::TestOnlineMonitorInFeatureQueue::test_anomaly_isolated_to_ip PASSED [ 97%]
tests/integration/test_online_inference_integration.py::TestAlertLoggerOnlineFields::test_log_alert_accepts_all_fields PASSED [100%]

============================== 37 passed in 4.44s ==============================
```

---
*Generated: 2026-06-01 10:13:52*
*Source: scripts/collect_demo_evidence.sh*
