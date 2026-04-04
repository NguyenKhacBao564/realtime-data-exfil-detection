"""
src/inference/alert_logger.py — Thread-safe alert formatting and logging.
"""

import logging
import time
from typing import Dict, Any, Optional

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


def format_alert(
    features: Dict[str, Any],
    burst_score: float,
    model_score: Optional[float] = None,
    prediction: Optional[int] = None,
    severity: str = "HIGH",
    color: bool = True,
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
    lines.append(f"{c}{b}  ── Scores ──{r}")
    lines.append(f"{c}  Burst score:   {b}{burst_score:.3f}{r}")
    if model_score is not None:
        lines.append(f"{c}  Model score:   {model_score:.3f}")
    if prediction is not None:
        pred_str = "EXFILTRATION" if prediction == 1 else "NORMAL"
        lines.append(f"{c}  Prediction:    {b}{pred_str}{r}")

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


class AlertLogger:
    """
    Thread-safe alert logger with console + file output.
    """

    def __init__(self, console_color: bool = True):
        self.logger = logging.getLogger("exfil.alerts")
        self.console_color = console_color
        self.alert_count = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        self.total_checked = 0

    def log_alert(
        self,
        features: Dict[str, Any],
        burst_score: float,
        model_score: Optional[float] = None,
        prediction: Optional[int] = None,
        severity: str = "HIGH",
    ):
        """Log a detection alert (both file and console)."""
        self.total_checked += 1
        self.alert_count[severity] = self.alert_count.get(severity, 0) + 1

        msg = format_alert(
            features, burst_score, model_score, prediction, severity,
            color=self.console_color,
        )

        # File log (no color)
        file_msg = format_alert(features, burst_score, model_score, prediction, severity, color=False)
        self.logger.warning(file_msg)

        # Console (with color)
        print(msg)

    def log_info(self, features: Dict[str, Any], burst_score: float):
        """Log a normal traffic info line."""
        self.total_checked += 1
        msg = format_info(features, burst_score, color=self.console_color)
        self.logger.info(f"{features.get('src_ip')} req={features.get('request_count')} score={burst_score:.3f}")
        print(msg)

    def log_error(self, message: str):
        """Log an error."""
        c = RED if self.console_color else ""
        r = RESET if self.console_color else ""
        print(f"{c}[ERROR] {message}{r}")
        self.logger.error(message)

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
