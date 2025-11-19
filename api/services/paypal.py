import requests
import logging
from django.conf import settings
from rest_framework.exceptions import APIException

logger = logging.getLogger(__name__)

class PayPalServiceError(APIException):
    status_code = 503
    default_detail = 'PayPal service unavailable'
    default_code = 'paypal_service_unavailable'

def get_paypal_access_token():
    client_id = settings.PAYPAL_CLIENT_ID
    secret = settings.PAYPAL_SECRET
    base_url = settings.PAYPAL_BASE_URL

    url = f"{base_url}/v1/oauth2/token"
    headers = {
        "Accept": "application/json",
        "Accept-Language": "en_US",
    }
    data = {"grant_type": "client_credentials"}
    
    try:
        response = requests.post(url, auth=(client_id, secret), data=data, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()["access_token"]
    except Exception as e:
        logger.error(f"PayPal Auth Failed: {e}")
        return None

def create_subscription(plan, shop, return_url, cancel_url):
    """
    Creates a subscription for a plan.
    Returns (subscription_id, approval_url)
    """
    token = get_paypal_access_token()
    if not token:
        raise PayPalServiceError()

    base_url = settings.PAYPAL_BASE_URL
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }

    # PayPal requires a plan_id. We assume it's stored in the plan object.
    paypal_plan_id = plan.paypal_plan_id
    if not paypal_plan_id:
         raise APIException("PayPal Plan ID not configured for this subscription plan.")

    payload = {
        "plan_id": paypal_plan_id,
        "subscriber": {
            "name": {
                "given_name": shop.owner.name or "Shop Owner",
                "surname": " " # PayPal requires surname sometimes, using space if empty
            },
            "email_address": shop.owner.email
        },
        "application_context": {
            "brand_name": "Fidden",
            "locale": "en-US",
            "shipping_preference": "NO_SHIPPING",
            "user_action": "SUBSCRIBE_NOW",
            "payment_method": {
                "payer_selected": "PAYPAL",
                "payee_preferred": "IMMEDIATE_PAYMENT_REQUIRED"
            },
            "return_url": return_url,
            "cancel_url": cancel_url
        },
        "custom_id": str(shop.id) # Store shop ID to identify it in webhooks
    }

    try:
        response = requests.post(f"{base_url}/v1/billing/subscriptions", json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        sub_id = data['id']
        approval_link = next(link['href'] for link in data['links'] if link['rel'] == 'approve')
        
        return sub_id, approval_link
    except Exception as e:
        logger.error(f"PayPal Create Subscription Failed: {e}")
        if hasattr(e, 'response') and e.response:
             logger.error(f"PayPal Response: {e.response.text}")
        raise APIException("Failed to create PayPal subscription")

def cancel_subscription(subscription_id, reason="Not specified"):
    token = get_paypal_access_token()
    if not token:
        raise PayPalServiceError()

    base_url = settings.PAYPAL_BASE_URL
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    
    url = f"{base_url}/v1/billing/subscriptions/{subscription_id}/cancel"
    payload = {"reason": reason}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        # 204 No Content is success
        if response.status_code == 204:
            return True
        response.raise_for_status()
    except Exception as e:
        logger.error(f"PayPal Cancel Subscription Failed: {e}")
        return False

def get_subscription_details(subscription_id):
    token = get_paypal_access_token()
    if not token:
        return None

    base_url = settings.PAYPAL_BASE_URL
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    
    url = f"{base_url}/v1/billing/subscriptions/{subscription_id}"
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        logger.error(f"PayPal Get Subscription Failed: {e}")
    return None

def revise_subscription(subscription_id, new_plan_id):
    """
    Upgrades or downgrades a subscription to a new plan.
    """
    token = get_paypal_access_token()
    if not token:
        raise PayPalServiceError()

    base_url = settings.PAYPAL_BASE_URL
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    
    url = f"{base_url}/v1/billing/subscriptions/{subscription_id}/revise"
    payload = {
        "plan_id": new_plan_id
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"PayPal Revise Subscription Failed: {e}")
        if hasattr(e, 'response') and e.response:
             logger.error(f"PayPal Response: {e.response.text}")
        raise APIException("Failed to update PayPal subscription")
