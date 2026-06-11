"""
src/inference/alert_logger.py — Thread-safe alert formatting and logging.
"""

import logging
import os
import time
import urllib.parse
import urllib.request
from typing import Dict, Any, Optional, List

from src.utils.config import PROJECT_ROOT

# ANSI color codes
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
MAGENTA= "\033[95m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"
DIM    = "\033[2m"

# Color mapping by severity
SEVERITY_COLORS = {
    "CRITICAL": RED,
    "HIGH":     MAGENTA,
    "MEDIUM":   YELLOW,
    "LOW":      CYAN,
    "INFO":     GREEN,
}

SEVERITY_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]


def load_alert_env():
    """Load local alert secrets from ignored env files if python-dotenv exists."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    # Keep exported shell variables higher priority than local files.
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    load_dotenv(PROJECT_ROOT / ".env.local", override=False)


def format_alert(
    features: Dict[str, Any],
    burst_score: float,
    model_score: Optional[float] = None,
    prediction: Optional[int] = None,
    severity: str = "HIGH",
    color: bool = True,
    online_score: Optional[float] = None,
    online_prediction: Optional[int] = None,
    online_reason_codes: Optional[List[str]] = None,
    baseline_count: Optional[int] = None,
    alert_triggers: Optional[List[str]] = None,
) -> str:
    """
    Format a detection alert for console and log output.

    Args:
        features: Window feature dict
        burst_score: burst_exfil_score (0-1)
        model_score: Optional model decision score
        prediction: Optional binary prediction (0/1)
        severity: Severity level string
        color: Whether to use ANSI colors

    Returns:
        Formatted multi-line alert string
    """
    ts = time.strftime("%Y-%m-%d %H:%M:%S")

    # Choose color
    c = SEVERITY_COLORS.get(severity, "") if color else ""
    r = RESET if color else ""
    b = BOLD if color else ""

    lines = []
    lines.append(f"{c}{b}━━━ EXFILTRATION ALERT ━━━{r}")
    lines.append(f"{c}{b}[{severity}]{r}  {ts}")
    lines.append(f"{c}  Source IP:     {b}{features.get('src_ip', 'unknown')}{r}")
    lines.append(f"{c}  Window start:  {features.get('window_start', 0):.0f}  ({time.strftime('%H:%M:%S', time.localtime(features.get('window_start', 0)))}  UTC)")
    lines.append(f"{c}  Requests:      {features.get('request_count', 0)}")
    lines.append(f"{c}  Total bytes:   {features.get('total_bytes', 0):,}  (↑{features.get('total_fwd_bytes', 0):,} / ↓{features.get('total_bwd_bytes', 0):,})")
    lines.append(f"{c}  Upload ratio:  {features.get('upload_download_ratio', 0):.2f}x")
    lines.append(f"{c}  Burst count:   {features.get('burst_count', 0)}  (ratio: {features.get('burst_ratio', 0):.2f})")
    lines.append(f"{c}  Unusual ports: {features.get('unusual_port_ratio', 0):.1%}")
    lines.append(f"{c}  Destinations: {features.get('unique_destinations', 0)}")
    lines.append(f"{c}  Session len:  {features.get('window_duration', 0):.1f}s")

    # Score breakdown
    # Alert triggers
    if alert_triggers:
        lines.append(f"{c}{b}  ── Triggers ──{r}")
        trigger_labels = {
            "BURST_RULE": "Burst exfil score",
            "OFFLINE_MODEL": "Offline model",
            "ONLINE_UNKNOWN_ANOMALY": "Online anomaly (unknown pattern)",
        }
        for t in alert_triggers:
            label = trigger_labels.get(t, t)
            lines.append(f"{c}  [{t}] {label}")

    # Score breakdown
    lines.append(f"{c}{b}  ── Scores ──{r}")
    lines.append(f"{c}  Burst score:   {b}{burst_score:.3f}{r}")
    if model_score is not None:
        lines.append(f"{c}  Model score:   {model_score:.3f}")
    if prediction is not None:
        pred_str = "EXFILTRATION" if prediction == 1 else "NORMAL"
        lines.append(f"{c}  Prediction:    {b}{pred_str}{r}")
    if online_score is not None:
        online_pred_str = "ANOMALY" if online_prediction == 1 else "NORMAL"
        lines.append(f"{c}  Online score:  {b}{online_score:.3f}{r}  ({online_pred_str})")
        if baseline_count is not None:
            lines.append(f"{c}  Baseline n:   {baseline_count}")
        if online_reason_codes:
            for code in online_reason_codes[:5]:
                lines.append(f"{c}    {DIM}{code}{r}")

    lines.append(f"{c}{b}━━━━━━━━━━━━━━━━━━━━━━━━{r}")

    return "\n".join(lines)


def format_info(
    features: Dict[str, Any],
    burst_score: float,
    color: bool = True,
) -> str:
    """Format INFO log for normal traffic."""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    dim = DIM if color else ""

    return (
        f"{dim}[INFO] {ts}  "
        f"IP={features.get('src_ip', '?')}  "
        f"req={features.get('request_count', 0)}  "
        f"bytes={features.get('total_bytes', 0):,}  "
        f"ratio={features.get('upload_download_ratio', 0):.2f}  "
        f"score={burst_score:.3f}{dim if color else ''}"
    )


def format_telegram_alert(
    features: Dict[str, Any],
    burst_score: float,
    model_score: Optional[float] = None,
    prediction: Optional[int] = None,
    severity: str = "HIGH",
    online_score: Optional[float] = None,
    online_prediction: Optional[int] = None,
    online_reason_codes: Optional[List[str]] = None,
) -> str:
    """Format metadata-only alert text for Telegram."""
    lines = [
        "EXFILTRATION ALERT",
        f"Severity: {severity}",
        f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Source IP: {features.get('src_ip', 'unknown')}",
        f"Requests: {features.get('request_count', 0)}",
        (
            f"Bytes: {features.get('total_bytes', 0):,} "
            f"(up {features.get('total_fwd_bytes', 0):,} / "
            f"down {features.get('total_bwd_bytes', 0):,})"
        ),
        f"Upload ratio: {features.get('upload_download_ratio', 0):.2f}x",
        f"Burst count: {features.get('burst_count', 0)}",
        f"Burst score: {burst_score:.3f}",
    ]
    if model_score is not None:
        lines.append(f"Model score: {model_score:.3f}")
    if prediction is not None:
        lines.append(f"Prediction: {'EXFILTRATION' if prediction == 1 else 'NORMAL'}")
    if online_score is not None:
        lines.append(f"Online score: {online_score:.3f} ({'ANOMALY' if online_prediction == 1 else 'NORMAL'})")
        if online_reason_codes:
            for code in online_reason_codes[:3]:
                lines.append(f"  {code}")
    lines.append("Payload content was not included.")
    return "\n".join(lines)


class AlertLogger:
    """
    Thread-safe alert logger with console + file output.
    """

    def __init__(self, console_color: bool = True):
        load_alert_env()
        self.logger = logging.getLogger("exfil.alerts")
        self.logger.propagate = False
        # Forward file handlers from root so alerts still reach exfil_detection.log
        root = logging.getLogger()
        for h in root.handlers:
            if isinstance(h, logging.FileHandler) and h not in self.logger.handlers:
                self.logger.addHandler(h)
        self.console_color = console_color
        self.alert_count = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        self.total_checked = 0
        self.telegram_enabled = os.getenv("ALERT_TELEGRAM_ENABLED", "").lower() in {
            "1", "true", "yes", "on"
        }
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if self.telegram_enabled and (not self.telegram_token or not self.telegram_chat_id):
            self.logger.warning(
                "Telegram alerting enabled but TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing"
            )

    def log_alert(
        self,
        features: Dict[str, Any],
        burst_score: float,
        model_score: Optional[float] = None,
        prediction: Optional[int] = None,
        severity: str = "HIGH",
        online_score: Optional[float] = None,
        online_prediction: Optional[int] = None,
        online_reason_codes: Optional[List[str]] = None,
        baseline_count: Optional[int] = None,
        alert_triggers: Optional[List[str]] = None,
    ):
        """Log a detection alert (both file and console)."""
        self.total_checked += 1
        self.alert_count[severity] = self.alert_count.get(severity, 0) + 1

        msg = format_alert(
            features, burst_score, model_score, prediction, severity,
            color=self.console_color,
            online_score=online_score,
            online_prediction=online_prediction,
            online_reason_codes=online_reason_codes,
            baseline_count=baseline_count,
            alert_triggers=alert_triggers,
        )

        # File log (no color)
        file_msg = format_alert(
            features, burst_score, model_score, prediction, severity, color=False,
            online_score=online_score,
            online_prediction=online_prediction,
            online_reason_codes=online_reason_codes,
            baseline_count=baseline_count,
            alert_triggers=alert_triggers,
        )
        self.logger.warning(file_msg)

        # Console (with color)
        print(msg)

        # Optional Telegram notification (metadata only, no payload content)
        self._send_telegram_alert(
            features, burst_score, model_score, prediction, severity,
            online_score=online_score, online_prediction=online_prediction,
            online_reason_codes=online_reason_codes,
        )

    def log_info(self, features: Dict[str, Any], burst_score: float):
        """Log a normal traffic window — silent (no per-window output to avoid console spam)."""
        self.total_checked += 1
        # Only log to file, skip console to avoid spam
        self.logger.debug(
            f"{features.get('src_ip')} req={features.get('request_count')} "
            f"score={burst_score:.3f} bytes={features.get('total_bytes', 0):,}"
        )

    def log_error(self, message: str):
        """Log an error."""
        c = RED if self.console_color else ""
        r = RESET if self.console_color else ""
        print(f"{c}[ERROR] {message}{r}")
        self.logger.error(message)

    def _send_telegram_alert(
        self,
        features: Dict[str, Any],
        burst_score: float,
        model_score: Optional[float],
        prediction: Optional[int],
        severity: str,
        online_score: Optional[float] = None,
        online_prediction: Optional[int] = None,
        online_reason_codes: Optional[List[str]] = None,
    ):
        """Send a best-effort Telegram alert if configured."""
        if not self.telegram_enabled:
            return
        if not self.telegram_token or not self.telegram_chat_id:
            return

        text = format_telegram_alert(
            features, burst_score, model_score, prediction, severity,
            online_score=online_score, online_prediction=online_prediction,
            online_reason_codes=online_reason_codes,
        )
        api_url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        body = urllib.parse.urlencode({
            "chat_id": self.telegram_chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        }).encode("utf-8")
        try:
            request = urllib.request.Request(api_url, data=body, method="POST")
            with urllib.request.urlopen(request, timeout=5) as response:
                if response.status >= 400:
                    self.logger.warning(f"Telegram alert failed with HTTP {response.status}")
        except Exception as e:
            self.logger.warning(f"Telegram alert failed: {e}")

    def summary(self) -> str:
        """Get alert summary."""
        total = sum(self.alert_count.values())
        if self.total_checked == 0:
            return "No windows processed yet."
        return (
            f"Summary: {total}/{self.total_checked} windows flagged "
            f"(CRITICAL={self.alert_count.get('CRITICAL', 0)} "
            f"HIGH={self.alert_count.get('HIGH', 0)} "
            f"MEDIUM={self.alert_count.get('MEDIUM', 0)} "
            f"LOW={self.alert_count.get('LOW', 0)})"
        )
