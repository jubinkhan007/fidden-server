from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from api.utils.fcm import notify_user
import logging
import traceback

logger = logging.getLogger(__name__)

def extract_validation_error_message(error):
    """
    Extract single error message from DRF ValidationError
    so we can return {"detail": "..."} consistently.
    """
    if hasattr(error, "detail"):
        if isinstance(error.detail, list):
            return str(error.detail[0]) if error.detail else "Validation error"
        elif isinstance(error.detail, dict):
            first_key = next(iter(error.detail))
            messages = error.detail[first_key]
            if isinstance(messages, list) and messages:
                return str(messages[0])
            return str(messages)
        return str(error.detail)
    return str(error)

def send_booking_reminder_email(booking, reminder_label):
    """
    Send an email reminder and push notification for a specific booking.
    """
    start_time_str = timezone.localtime(booking.slot.start_time).strftime("%A, %d %B %Y at %I:%M %p")
    end_time_str = timezone.localtime(booking.slot.end_time).strftime("%I:%M %p")
    service_title = booking.slot.service.title
    shop_name = booking.shop.name
    customer_name = booking.user.name or booking.user.email

    # ---------------- Email ----------------
    subject = f"Reminder: Your upcoming booking ({reminder_label.replace('_', ' ').title()})"

    message = (
        f"Hello {customer_name},\n\n"
        f"This is a reminder for your upcoming booking.\n\n"
        f"🏬 Shop: {shop_name}\n"
        f"💆 Service: {service_title}\n"
        f"🗓 Date & Time: {start_time_str} – {end_time_str}\n"
        f"⏰ Reminder type: {reminder_label.replace('_', ' ').title()}\n\n"
        f"Thank you for choosing us!"
    )

    from_email = settings.DEFAULT_FROM_EMAIL
    to_email = [booking.user.email]

    try:
        send_mail(subject, message, from_email, to_email)
    except Exception as e:
        logger.error(
            "Failed to send reminder email for Booking %s (%s): %s\n%s",
            booking.id,
            reminder_label,
            str(e),
            traceback.format_exc()
        )

    # ---------------- Push Notification ----------------
    try:
        notify_user(
            booking.user,
            message=(
                f"Reminder: Your booking for {service_title} at {shop_name} "
                f"is coming up on {start_time_str} ({reminder_label.replace('_', ' ').title()})."
            ),
            notification_type="booking_reminder",
            data={
                "booking_id": booking.id,
                "shop_id": booking.shop.id,
                "service": service_title,
                "start_time": str(booking.slot.start_time),
                "end_time": str(booking.slot.end_time),
                "reminder_type": reminder_label,
            },
        )
    except Exception as e:
        logger.error(
            "Failed to send push reminder for Booking %s (%s): %s\n%s",
            booking.id,
            reminder_label,
            str(e),
            traceback.format_exc()
        )
