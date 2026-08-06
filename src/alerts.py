from __future__ import annotations

import json
import logging
import os
import urllib.request

import pandas as pd

log = logging.getLogger("macro_pulse.alerts")


def compose_alerts(episodes: pd.DataFrame | None,
                   latest_data_date,
                   scorecard: pd.DataFrame | None,
                   stress_threshold: float = 1.0) -> list[str]:
    """Pure function: returns the list of alert messages (possibly empty)."""
    msgs = []
    if episodes is not None and not episodes.empty and latest_data_date:
        last = episodes.iloc[-1]
        if pd.Timestamp(last["end"]) >= pd.Timestamp(latest_data_date):
            msgs.append(
                f"🔻 Macro Pulse: yield curve INVERTED — episode since "
                f"{last['start']}, {last['trading_days']} trading days, "
                f"min {last['min_bp']} bp.")
    if scorecard is not None and not scorecard.empty:
        hot = scorecard[scorecard["stress_index"] > stress_threshold]
        for _, row in hot.iterrows():
            msgs.append(
                f"⚠️ Macro Pulse: {row['country']} stress index "
                f"{row['stress_index']:+.2f} above threshold "
                f"{stress_threshold:+.2f}.")
    return msgs


def send_alerts(messages: list[str], alerts_cfg: dict) -> int:
    """Send messages via whichever webhooks are configured; returns #sent."""
    if not messages:
        return 0
    sent = 0
    slack_url = os.environ.get(alerts_cfg.get("slack_webhook_env", ""), "")
    tg_token = os.environ.get(alerts_cfg.get("telegram_token_env", ""), "")
    tg_chat = os.environ.get(alerts_cfg.get("telegram_chat_env", ""), "")
    for msg in messages:
        log.info("ALERT: %s", msg)
        if slack_url:
            _post(slack_url, {"text": msg})
            sent += 1
        if tg_token and tg_chat:
            _post(f"https://api.telegram.org/bot{tg_token}/sendMessage",
                  {"chat_id": tg_chat, "text": msg})
            sent += 1
    if not slack_url and not (tg_token and tg_chat):
        log.info("(no webhook configured — alerts logged only)")
    return sent


def _post(url: str, payload: dict) -> None:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:                    
        log.warning("alert delivery failed: %s", exc)
