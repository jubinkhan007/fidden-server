# api/utils/sms.py
from django.conf import settings
from twilio.rest import Client
import logging

logger = logging.getLogger(__name__)

def send_sms(to_number: str, body: str) -> bool:
    """
    Sends an SMS via Twilio.
    - Prefer Messaging Service if TWILIO_MESSAGING_SERVICE_SID is set.
    - Fallback to TWILIO_FROM_NUMBER.
    - `to_number` must be in E.164 format (e.g., +14155552671).
    Returns True if Twilio accepted/queued the message (or test flow OK).
    """

    if not getattr(settings, "TWILIO_ENABLE", True):
        logger.info("Twilio disabled by settings.TWILIO_ENABLE=False")
        return False

    account_sid = getattr(settings, "TWILIO_ACCOUNT_SID", "")
    auth_token = getattr(settings, "TWILIO_AUTH_TOKEN", "")
    from_number = getattr(settings, "TWILIO_FROM_NUMBER", "") or ""
    messaging_service_sid = getattr(settings, "TWILIO_MESSAGING_SERVICE_SID", "") or ""

    if not account_sid or not auth_token:
        logger.error("Twilio credentials missing (ACCOUNT_SID/AUTH_TOKEN).")
        return False

    if not to_number:
        logger.warning("send_sms: missing 'to_number'")
        return False

    if not to_number.startswith("+"):
        logger.warning("send_sms: 'to_number' must be E.164; got %s", to_number)
        return False

    try:
        client = Client(account_sid, auth_token)
        kwargs = {"to": to_number, "body": body}

        use_ms = bool(messaging_service_sid)
        if use_ms:
            kwargs["messaging_service_sid"] = messaging_service_sid
            logger.info("send_sms: using Messaging Service SID %s", messaging_service_sid[:10] + "…")
        elif from_number:
            kwargs["from_"] = from_number
            logger.info("send_sms: using From number %s", from_number)
        else:
            logger.error("Configure TWILIO_MESSAGING_SERVICE_SID or TWILIO_FROM_NUMBER")
            return False

        try:
            msg = client.messages.create(**kwargs)
            logger.info("SMS accepted by Twilio. To=%s Sid=%s Status=%s",
                        to_number, getattr(msg, "sid", "?"), getattr(msg, "status", "?"))
            return True
        except Exception as primary_err:
            # Auto-fallback: if MS SID failed and we have a from_number, retry with from_
            if use_ms and from_number:
                logger.warning("send_sms: MS SID send failed (%s). Retrying with from_=%s",
                               primary_err.__class__.__name__, from_number)
                kwargs.pop("messaging_service_sid", None)
                kwargs["from_"] = from_number
                msg = client.messages.create(**kwargs)
                logger.info("SMS accepted by Twilio (fallback). To=%s Sid=%s Status=%s",
                            to_number, getattr(msg, "sid", "?"), getattr(msg, "status", "?"))
                return True
            raise

    except Exception as e:
        logger.error("Failed to send SMS to %s: %s", to_number, e, exc_info=True)
        return False
