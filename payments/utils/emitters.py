# payments/utils/emitters.py
from datetime import datetime, timezone
import logging, requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

def ts_to_iso(ts):
    # robust for int/None
    return datetime.fromtimestamp(int(ts), tz=datetime.timezone.utc).isoformat()

def emit_subscription_updated_to_zapier(sub, shop, previous_plan_name, current_plan_name, extra_fields=None):
    """
    sub: stripe.Subscription (expanded with items & latest_invoice.*)
    shop: Shop model instance
    previous_plan_name/current_plan_name: strings you derive from DB before/after change
    """
    latest_invoice = sub.get("latest_invoice")
    if isinstance(latest_invoice, str):
        # If only ID returned, retrieve expanded invoice in the caller and pass that in instead,
        # or expand in the original Subscription.retrieve (recommended).
        logger.warning("emit_subscription_updated_to_zapier got unexpanded invoice; event may be missing fields.")
        invoice_id = latest_invoice
        amount_paid = None
        currency = None
        period_start_iso = ts_to_iso(sub.get("current_period_start"))
        period_end_iso = ts_to_iso(sub.get("current_period_end"))
    else:
        invoice_id = latest_invoice.get("id")
        amount_paid = latest_invoice.get("amount_paid")  # cents
        currency = latest_invoice.get("currency")

        # prefer invoice period if present, else subscription period
        lines = (latest_invoice.get("lines") or {}).get("data") or []
        if lines and isinstance(lines[0], dict) and "period" in lines[0]:
            period = lines[0]["period"]
            period_start_iso = ts_to_iso(period.get("start"))
            period_end_iso = ts_to_iso(period.get("end"))
        else:
            period_start_iso = ts_to_iso(sub.get("current_period_start"))
            period_end_iso = ts_to_iso(sub.get("current_period_end"))

    items = (sub.get("items") or {}).get("data") or []
    price_id = ((items[0] or {}).get("price") or {}).get("id") if items else None

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
        "period_start_iso": ts_to_iso(sub.get("current_period_start")),
        "period_end_iso": ts_to_iso(sub.get("current_period_end")),
        "next_billing_date_iso": ts_to_iso(sub.get("current_period_end")),
        "invoice_id": invoice_id,
        "payment_intent_id": payment_intent_id,
        "charge_id": charge_id,
        "amount_paid": amount_paid,
        "currency": currency,
        "dedupe_key": f"{sub.get('id')}:{ts_to_iso(sub.get('current_period_start'))}",
    }

    if extra_fields:
        payload.update(extra_fields)

    try:
        requests.post(settings.ZAPIER_KLAVIYO_WEBHOOK, json=payload, timeout=10)
    except Exception:
        logger.exception("[zapier] emit_subscription_updated_to_zapier failed")

    try:
        hook = settings.ZAPIER_SUBSCRIPTION_UPDATED_HOOK
        if not hook:
            logger.error("ZAPIER_SUBSCRIPTION_UPDATED_HOOK not set; skipping emit.")
            return
        r = requests.post(hook, json=payload, timeout=10)
        r.raise_for_status()
        logger.info("[zapier] emitted Subscription Updated for %s", sub.get("id"))
    except Exception as e:
        logger.exception("[zapier] emit failed for %s: %s", sub.get("id"), e)
