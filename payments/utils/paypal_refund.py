"""
PayPal Refund Utility
Handles refunding PayPal captured payments
"""
import requests
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def get_paypal_access_token():
    """Get PayPal OAuth access token."""
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
        response = requests.post(url, auth=(client_id, secret), data=data, headers=headers)
        response.raise_for_status()
        return response.json()["access_token"]
    except Exception as e:
        logger.error(f"PayPal Auth Failed: {e}")
        return None


def process_paypal_refund(capture_id: str, amount: float, reason: str = None) -> dict:
    """
    Process a PayPal refund for a captured payment.
    
    Args:
        capture_id: The PayPal capture ID from the original payment
        amount: Amount to refund in dollars
        reason: Optional reason for refund (for internal tracking)
    
    Returns:
        dict with 'success', 'refund_id', and 'error' keys
    """
    if not capture_id:
        return {'success': False, 'error': 'No capture ID provided'}
    
    token = get_paypal_access_token()
    if not token:
        return {'success': False, 'error': 'Failed to get PayPal access token'}
    
    base_url = settings.PAYPAL_BASE_URL
    url = f"{base_url}/v2/payments/captures/{capture_id}/refund"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    
    # PayPal refund payload
    payload = {
        "amount": {
            "value": f"{amount:.2f}",
            "currency_code": "USD"
        },
        "note_to_payer": reason or "Booking cancelled per cancellation policy"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code in [200, 201]:
            data = response.json()
            refund_id = data.get("id")
            status = data.get("status")
            
            logger.info(f"PayPal refund successful: {refund_id} - Status: {status}")
            
            return {
                'success': True,
                'refund_id': refund_id,
                'status': status,
                'amount': amount
            }
        else:
            error_data = response.json()
            error_message = error_data.get("message", "Unknown PayPal error")
            logger.error(f"PayPal refund failed: {response.status_code} - {error_message}")
            
            return {
                'success': False,
                'error': error_message,
                'status_code': response.status_code
            }
            
    except Exception as e:
        logger.error(f"PayPal refund exception: {str(e)}")
        return {'success': False, 'error': str(e)}
