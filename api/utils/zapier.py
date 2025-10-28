# api/utils/zapier.py
import json
import logging
import requests
from django.conf import settings
from django.utils import timezone
from decimal import Decimal

logger = logging.getLogger(__name__)

ZAPIER_WEBHOOK_URL = getattr(
    settings,
    "ZAPIER_KLAVIYO_WEBHOOK",
    None,
)

def _json_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    return str(obj)

def send_klaviyo_event(
    *,
    email: str,
    event_name: str,
    profile: dict,
    event_props: dict | None = None,
):
    if not ZAPIER_WEBHOOK_URL:
        logger.warning("[klaviyo] ZAPIER_KLAVIYO_WEBHOOK not configured; skipping")
        return False

    payload = {
        "email": email,
        "event_name": event_name,
        "profile": profile,
        "event_props": event_props or {},
        "sent_at": timezone.now().isoformat(),
    }

    try:
        resp = requests.post(
            ZAPIER_WEBHOOK_URL,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload, default=_json_default),
            timeout=3,
        )
        logger.info(
            "[klaviyo] event=%s email=%s status=%s resp=%s",
            event_name,
            email,
            resp.status_code,
            resp.text[:200],
        )
        return resp.ok
    except Exception as e:
        logger.error(
            "[klaviyo] failed to send event=%s email=%s err=%s",
            event_name,
            email,
            e,
            exc_info=True,
        )
        return False
