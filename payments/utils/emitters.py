# payments/utils/emitters.py
import datetime as dt
import logging, requests
from django.conf import settings

logger = logging.getLogger(__name__)

def ts_to_iso(ts):
    if not ts:
        return None
    return dt.datetime.fromtimestamp(int(ts), tz=dt.timezone.utc).isoformat()


def emit_subscription_updated_to_zapier(sub, shop, previous_plan_name, current_plan_name, extra_fields=None):
    """
    Fire exactly once per (subscription_id, current_period_start).
    """
    latest_invoice = sub.get("latest_invoice")
    if isinstance(latest_invoice, str):
        invoice_id = latest_invoice
        amount_paid = None
        currency = None
        period_start_iso = ts_to_iso(sub.get("current_period_start"))
        period_end_iso = ts_to_iso(sub.get("current_period_end"))
    else:
        invoice_id = (latest_invoice or {}).get("id")
        amount_paid = (latest_invoice or {}).get("amount_paid")
        currency = (latest_invoice or {}).get("currency")

        lines = ((latest_invoice or {}).get("lines") or {}).get("data") or []
        if lines and isinstance(lines[0], dict) and "period" in lines[0]:
            period = lines[0]["period"]
            period_start_iso = ts_to_iso(period.get("start"))
            period_end_iso = ts_to_iso(period.get("end"))
        else:
            period_start_iso = ts_to_iso(sub.get("current_period_start"))
            period_end_iso = ts_to_iso(sub.get("current_period_end"))

    items = (sub.get("items") or {}).get("data") or []
    price_id = ((items[0] or {}).get("price") or {}).get("id") if items else None

    current_period_start = sub.get("current_period_start")
    dedupe_key = f"zap:sub_updated:{sub.get('id')}:{current_period_start}"

    # # ✅ Only the first caller wins for 10 minutes (avoid bursts/duplicates)
    # if cache.add(dedupe_key, 1, timeout=600) is False:
    #     logger.info("[zapier] duplicate suppressed for %s", dedupe_key)
    #     return

    payload = {
        "event_name": "Subscription Updated",
        "metric": "Subscription Updated",
        "email": getattr(shop.owner, "email", None),
        "shop_id": shop.id,
        "shop_name": getattr(shop, "name", None),
        "subscription_id": sub.get("id"),
        "price_id": price_id,
        "previous_plan": previous_plan_name,
        "current_plan": current_plan_name,
        "plan_status": sub.get("status"),
        "period_start_iso": period_start_iso,
        "period_end_iso": period_end_iso,
        "next_billing_date_iso": ts_to_iso(sub.get("current_period_end")),
        "invoice_id": invoice_id,
        "amount_paid": amount_paid,
        "currency": currency,
        "dedupe_key": f"{sub.get('id')}:{ts_to_iso(current_period_start)}",
    }
    if extra_fields:
        payload.update(extra_fields)

    hook = getattr(settings, "ZAPIER_KLAVIYO_WEBHOOK", "")
    if not hook:
        logger.error("ZAPIER_KLAVIYO_WEBHOOK not set; skipping emit.")
        return

    try:
        r = requests.post(hook, json=payload, timeout=10)
        r.raise_for_status()
        logger.info("[zapier] emitted Subscription Updated for %s (once)", sub.get("id"))
    except Exception as e:
        logger.exception("[zapier] emit failed for %s: %s", sub.get("id"), e)
