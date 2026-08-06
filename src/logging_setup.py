"""Structured logging for unattended runs (GitHub Actions, cron, Docker).

Console keeps the human-friendly format; a rotating file under
outputs/logs/ captures full detail so a scheduled run leaves a trail.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[1] / "outputs" / "logs"


def setup_logging(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger("macro_pulse")
    if logger.handlers:            # idempotent — safe to call twice
        return logger
    logger.setLevel(logging.DEBUG)

    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    filehandler = RotatingFileHandler(LOG_DIR / "macro_pulse.log",
                                      maxBytes=1_000_000, backupCount=3,
                                      encoding="utf-8")
    filehandler.setLevel(logging.DEBUG)
    filehandler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    logger.addHandler(filehandler)
    return logger
