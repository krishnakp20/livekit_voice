"""Push the data collected on a call to the client's CRM webhook.

Configured per agent via ai_agents.webhook_json:

    {
      "url": "https://crmapi.example.com/bot/webhook-api",
      "headers": {"Content-Type": "application/json", "Auth-Token": "..."},
      "payload_template": {"Calling Phone no.": "", "City ": "", ...}
    }

payload_template is the CRM's own "Request Data" JSON pasted verbatim. Its keys may
contain spaces, capitals and even trailing blanks ("City ") — we keep them EXACTLY as
given and fill the values by matching against our normalised extraction keys, so the
CRM receives its own field names with no mapping table to maintain.
"""

import json
import logging
import re

logger = logging.getLogger("vbots.crm_webhook")

_TIMEOUT_SECONDS = 15


def _norm(key: str) -> str:
    """Mirror the UI's data-field key normalisation: trim → spaces to '_' → lowercase.

    So a CRM template key 'Calling Phone no.' matches our stored 'calling_phone_no.',
    and 'City ' (trailing space) matches 'city'."""
    return re.sub(r"\s+", "_", (key or "").strip()).lower()


def build_payload(template: dict | None, data: dict) -> dict:
    """Fill the CRM's exact field names from the collected data.

    Missing values become "" so the CRM always receives the full field set."""
    if not template:
        return dict(data or {})
    normalised = {_norm(k): v for k, v in (data or {}).items()}
    out: dict = {}
    for crm_key in template:
        value = normalised.get(_norm(crm_key), "")
        out[crm_key] = "" if value is None else value
    return out


async def send_call_webhook(agent, data: dict, call_id: int) -> None:
    """POST the collected data to the agent's CRM webhook. No-op if not configured."""
    raw = (getattr(agent, "webhook_json", "") or "").strip()
    if not raw:
        return

    try:
        cfg = json.loads(raw)
    except (ValueError, TypeError):
        logger.warning("webhook_json is not valid JSON (agent_id=%s)", getattr(agent, "id", "?"))
        return
    if not isinstance(cfg, dict):
        return

    url = (cfg.get("url") or "").strip()
    if not url:
        return

    headers = cfg.get("headers") or {"Content-Type": "application/json"}
    payload = build_payload(cfg.get("payload_template"), data)

    try:
        import aiohttp

        timeout = aiohttp.ClientTimeout(total=_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                body = (await resp.text())[:300]
                if 200 <= resp.status < 300:
                    logger.info(
                        "CRM webhook sent call_id=%s status=%s response=%s",
                        call_id, resp.status, body,
                    )
                else:
                    logger.warning(
                        "CRM webhook FAILED call_id=%s status=%s response=%s payload=%s",
                        call_id, resp.status, body, payload,
                    )
    except Exception as e:  # never let a CRM outage break call teardown
        logger.warning("CRM webhook error call_id=%s url=%s: %s", call_id, url, e)
