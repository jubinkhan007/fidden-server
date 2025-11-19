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

def create_subscription(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    """
    TEMPORARY STUB.

    We define this so imports in subscriptions/views.py work and the app boots.

    When you’re ready to integrate real PayPal subscriptions, replace this
    implementation with a proper call to:
      POST /v1/billing/subscriptions

    For now we just log and return a fake payload.
    """
    logger.warning(
        "PayPal create_subscription() called, but this is currently a stub. "
        "No real PayPal API call is performed."
    )
    return {
        "status": "stub",
        "id": None,
        "message": "PayPal create_subscription is not implemented yet.",
    }


def revise_subscription(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    """
    TEMPORARY STUB.

    Same story as create_subscription: we just satisfy imports so the app
    doesn’t crash. Replace with real logic later if/when PayPal is needed.
    """
    logger.warning(
        "PayPal revise_subscription() called, but this is currently a stub. "
        "No real PayPal API call is performed."
    )
    return {
        "status": "stub",
        "id": None,
        "message": "PayPal revise_subscription is not implemented yet.",
    }


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
