from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def verify_google_token(token):
    """
    Verify Google ID token against multiple client IDs.

    Args:
        token (str): The Google ID token.

    Returns:
        dict or None: User info dict if verified, else None.
    """
    for client_id in settings.GOOGLE_CLIENT_IDS.values():
        try:
            idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), client_id)
            email = idinfo.get('email')
            email_verified = idinfo.get('email_verified')
            if email and email_verified:
                return {
                    "email": email,
                    "name": idinfo.get("name"),
                    "picture": idinfo.get("picture"),
                    "sub": idinfo.get("sub"),
                }
        except ValueError as e:
            logger.debug(f"Token verification failed for client_id {client_id}: {e}")
            continue  # try next client_id
    logger.warning("Google token verification failed for all client IDs.")
    return None
