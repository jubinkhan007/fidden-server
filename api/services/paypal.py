# api/services/paypal.py

import base64
import logging
from typing import Optional, Any, Dict

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def _get_paypal_base_url() -> str:
    """
    Returns the base URL for PayPal API.
    Override via PAYPAL_BASE_URL in settings if needed.
    """
    return getattr(settings, "PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com")


def _get_paypal_credentials() -> tuple[str, str]:
    """
    Fetch client ID and secret from Django settings.
    """
    client_id: Optional[str] = getattr(settings, "PAYPAL_CLIENT_ID", None)
    secret: Optional[str] = getattr(settings, "PAYPAL_SECRET", None)

    if not client_id or not secret:
        raise RuntimeError(
            "PAYPAL_CLIENT_ID and PAYPAL_SECRET must be set in Django settings "
            "to use PayPal subscription APIs."
        )
    return client_id, secret


def _get_access_token() -> str:
    """
    Get an app access token from PayPal using client credentials.
    """
    client_id, secret = _get_paypal_credentials()
    base_url = _get_paypal_base_url()

    basic_auth = base64.b64encode(f"{client_id}:{secret}".encode("utf-8")).decode(
        "utf-8"
    )

    resp = requests.post(
        f"{base_url}/v1/oauth2/token",
        headers={
            "Authorization": f"Basic {basic_auth}",
            "Accept": "application/json",
            "Accept-Language": "en_US",
        },
        data={"grant_type": "client_credentials"},
        timeout=10,
    )

    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        logger.error("Failed to get PayPal access token: %s | body=%s", e, resp.text)
        raise

    data = resp.json()
    token = data.get("access_token")
    if not token:
        logger.error("PayPal token response missing access_token: %s", data)
        raise RuntimeError("PayPal access token missing in response")

    return token


# ---------------------------------------------------------------------------
# STUBS – create_subscription & revise_subscription
# ---------------------------------------------------------------------------

def create_subscription(
    plan: Any,
    shop: Any,
    return_url: str,
    cancel_url: str
) -> tuple[str, str]:
    """
    Creates a subscription in PayPal.

    Args:
        plan: The SubscriptionPlan model instance.
        shop: The Shop model instance.
        return_url: URL to redirect after approval.
        cancel_url: URL to redirect after cancellation.

    Returns:
        (subscription_id, approval_url)
    """
    if not plan.paypal_plan_id:
        raise ValueError(f"Plan {plan.name} has no paypal_plan_id configured.")

    access_token = _get_access_token()
    base_url = _get_paypal_base_url()

    # Construct the subscription payload
    # See: https://developer.paypal.com/docs/api/subscriptions/v1/#subscriptions_create
    payload = {
        "plan_id": plan.paypal_plan_id,
        "custom_id": str(shop.id),  # Store shop ID for reconciliation
        "application_context": {
            "brand_name": "Fidden",
            "locale": "en-US",
            "shipping_preference": "NO_SHIPPING",
            "user_action": "SUBSCRIBE_NOW",
            "return_url": return_url,
            "cancel_url": cancel_url,
        },
    }

    logger.info("Creating PayPal subscription for shop %s, plan %s", shop.id, plan.paypal_plan_id)

    resp = requests.post(
        f"{base_url}/v1/billing/subscriptions",
        json=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        timeout=15,
    )

    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        logger.error("PayPal create subscription failed: %s | body=%s", e, resp.text)
        raise

    data = resp.json()
    sub_id = data.get("id")
    links = data.get("links", [])
    approval_url = next((link["href"] for link in links if link["rel"] == "approve"), None)

    if not sub_id or not approval_url:
        logger.error("PayPal response missing id or approval_url: %s", data)
        raise RuntimeError("Invalid PayPal subscription response")

    return sub_id, approval_url


def revise_subscription(subscription_id: str, new_plan_id: str) -> Dict[str, Any]:
    """
    Upgrades or downgrades an existing subscription to a new plan.
    
    Args:
        subscription_id: The PayPal subscription ID (I-...)
        new_plan_id: The PayPal Plan ID (P-...) to switch to.
        
    Returns:
        The JSON response from PayPal.
    """
    if not subscription_id or not new_plan_id:
        raise ValueError("subscription_id and new_plan_id are required")

    access_token = _get_access_token()
    base_url = _get_paypal_base_url()
    
    url = f"{base_url}/v1/billing/subscriptions/{subscription_id}/revise"
    
    payload = {
        "plan_id": new_plan_id
    }
    
    logger.info("Revising PayPal subscription %s to plan %s", subscription_id, new_plan_id)
    
    resp = requests.post(
        url,
        json=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        timeout=15,
    )
    
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        logger.error("PayPal revise subscription failed: %s | body=%s", e, resp.text)
        raise

    return resp.json()


# ---------------------------------------------------------------------------
# REAL IMPLEMENTATION – cancel_subscription
# ---------------------------------------------------------------------------

def cancel_subscription(subscription_id: str, reason: str = "Cancelled in app") -> None:
    """
    Cancel a PayPal subscription via REST API.

    Will:
      - Fetch an access token
      - Call POST /v1/billing/subscriptions/{id}/cancel

    Raises requests.HTTPError if PayPal returns an error.
    """
    if not subscription_id:
        raise ValueError("subscription_id is required")

    base_url = _get_paypal_base_url()
    access_token = _get_access_token()

    url = f"{base_url}/v1/billing/subscriptions/{subscription_id}/cancel"
    payload = {"reason": reason}

    logger.info("Cancelling PayPal subscription %s", subscription_id)

    resp = requests.post(
        url,
        json=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        timeout=10,
    )

    # PayPal usually returns 204 No Content on success
    if resp.status_code not in (200, 202, 204):
        logger.error(
            "PayPal cancel failed. status=%s body=%s", resp.status_code, resp.text
        )
        resp.raise_for_status()

    logger.info("PayPal subscription %s cancelled successfully", subscription_id)
