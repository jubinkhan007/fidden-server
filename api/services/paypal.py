# api/services/paypal.py

import logging
from typing import Any, Optional

from django.conf import settings

from paypalcheckoutsdk.core import (
    PayPalHttpClient,
    SandboxEnvironment,
    LiveEnvironment,
)
from paypalhttp.http_request import HttpRequest  # from `paypalhttp` package

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------
# Low-level request classes (PayPal Python SDK does NOT ship
# a `subscriptions` module, so we build these around HttpRequest).
# -------------------------------------------------------------------


class SubscriptionsCreateRequest(HttpRequest):
    def __init__(self) -> None:
        # POST /v1/billing/subscriptions
        super().__init__("/v1/billing/subscriptions", "POST")
        self.headers["prefer"] = "return=representation"
        self.headers["content-type"] = "application/json"


class SubscriptionsCancelRequest(HttpRequest):
    def __init__(self, subscription_id: str) -> None:
        # POST /v1/billing/subscriptions/{id}/cancel
        super().__init__(f"/v1/billing/subscriptions/{subscription_id}/cancel", "POST")
        self.headers["content-type"] = "application/json"


class SubscriptionsReviseRequest(HttpRequest):
    def __init__(self, subscription_id: str) -> None:
        # POST /v1/billing/subscriptions/{id}/revise
        super().__init__(f"/v1/billing/subscriptions/{subscription_id}/revise", "POST")
        self.headers["prefer"] = "return=representation"
        self.headers["content-type"] = "application/json"


# -------------------------------------------------------------------
# Client factory
# -------------------------------------------------------------------


def _get_paypal_client() -> Any:
    """
    Lazily construct a PayPal client using env vars from settings.
    Return type is Any so Pylance doesn't complain when imports are dynamic.
    """
    client_id = getattr(settings, "PAYPAL_CLIENT_ID", None)
    client_secret = getattr(settings, "PAYPAL_CLIENT_SECRET", None) or getattr(
        settings, "PAYPAL_SECRET", None
    )

    if not client_id or not client_secret:
        raise RuntimeError("PayPal credentials not configured (PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET)")

    env_name = getattr(settings, "PAYPAL_ENVIRONMENT", "sandbox")
    EnvironmentClass = SandboxEnvironment if env_name == "sandbox" else LiveEnvironment

    env = EnvironmentClass(
        client_id=client_id,
        client_secret=client_secret,
    )
    return PayPalHttpClient(env)


# -------------------------------------------------------------------
# High-level helpers used by your views
# -------------------------------------------------------------------


def create_subscription(plan, shop, return_url: str, cancel_url: str):
    """
    Create a PayPal subscription for the given SubscriptionPlan and Shop.
    Returns (subscription_id, approval_url).
    Expects `plan.paypal_plan_id` to be set.
    """
    client = _get_paypal_client()
    request = SubscriptionsCreateRequest()

    body = {
        "plan_id": plan.paypal_plan_id,
        "subscriber": {
            "email_address": shop.owner.email,  # adjust if your owner model differs
        },
        "application_context": {
            "brand_name": "Fidden",
            "user_action": "SUBSCRIBE_NOW",
            "return_url": return_url,
            "cancel_url": cancel_url,
        },
    }

    request.request_body(body)

    response = client.execute(request)
    result = response.result

    approval_url = None
    for link in getattr(result, "links", []):
        if getattr(link, "rel", None) == "approve":
            approval_url = getattr(link, "href", None)
            break

    subscription_id = getattr(result, "id", None)
    logger.info("Created PayPal subscription %s for shop %s", subscription_id, shop.id)
    return subscription_id, approval_url


def cancel_subscription(subscription_id: str, reason: str = "User requested cancellation"):
    """
    Cancel a PayPal subscription.
    """
    client = _get_paypal_client()
    request = SubscriptionsCancelRequest(subscription_id)
    request.request_body({"reason": reason})
    response = client.execute(request)
    logger.info("Cancelled PayPal subscription %s (%s)", subscription_id, reason)
    return response


def revise_subscription(
    subscription_id: str,
    new_plan_id: str,
    *,
    return_url: Optional[str] = None,
    cancel_url: Optional[str] = None,
):
    """
    Revise an existing PayPal subscription to a different plan.

    Returns (subscription_id, approval_url | None)

    - If PayPal needs the user to re-approve, you'll get an `approve` link.
    - If not, `approval_url` will be None and the change is immediate.
    """
    client = _get_paypal_client()
    request = SubscriptionsReviseRequest(subscription_id)

    body: dict[str, Any] = {
        "plan_id": new_plan_id,
    }

    if return_url or cancel_url:
        body["application_context"] = {
            "return_url": return_url,
            "cancel_url": cancel_url,
        }

    request.request_body(body)
    response = client.execute(request)
    result = response.result

    approval_url = None
    for link in getattr(result, "links", []):
        if getattr(link, "rel", None) == "approve":
            approval_url = getattr(link, "href", None)
            break

    logger.info(
        "Revised PayPal subscription %s → plan %s (approval_url=%s)",
        subscription_id,
        new_plan_id,
        bool(approval_url),
    )
    return getattr(result, "id", subscription_id), approval_url
