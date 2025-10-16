from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from accounts.models import User
from api.utils.fcm import notify_user
from payments.models import Booking
from .utils.helper_function import send_booking_reminder_email
import logging
import traceback

logger = logging.getLogger(__name__)


@shared_task
def complete_past_bookings():
    """
    Automatically mark bookings as completed if their linked SlotBooking has ended.
    """
    now = timezone.now()

    # Fetch active bookings where the linked SlotBooking has ended
    bookings_to_complete = Booking.objects.filter(
        status='active',
        slot__end_time__lte=now
    )

    count = bookings_to_complete.count()
    for booking in bookings_to_complete:
        booking.status = 'completed'
        booking.save(update_fields=['status', 'updated_at'])
        print(f"Booking {booking.id} marked as completed")

    return f"{count} bookings completed"





@shared_task
def send_booking_reminders():
    """
    Send reminders to users for their active bookings:
    - 1 day before
    - 1 hour before
    - 15 minutes before
    """
    now = timezone.now()

    try:
        bookings = Booking.objects.filter(status="active").select_related("slot", "user", "shop")

        reminders_sent = 0

        for booking in bookings:
            slot_end = booking.slot.end_time
            slot_start = booking.slot.start_time

            # Check if the booking is still in the future
            if slot_start <= now:
                continue

            reminder_times = {
                "1_day": slot_start - timedelta(days=1),
                "1_hour": slot_start - timedelta(hours=1),
                "15_minutes": slot_start - timedelta(minutes=15),
            }

            for reminder_label, reminder_time in reminder_times.items():
                # Allow a 1 minute window to send the reminder
                if reminder_time <= now <= reminder_time + timedelta(minutes=1):
                    try:
                        send_booking_reminder_email(booking, reminder_label)
                        reminders_sent += 1
                    except Exception as e:
                        logger.error(
                            "Failed to send booking reminder for Booking %s (%s): %s\n%s",
                            booking.id,
                            reminder_label,
                            str(e),
                            traceback.format_exc()
                        )

        return f"{reminders_sent} booking reminders sent."
    except Exception as e:
        logger.error("Error in send_booking_reminders task: %s\n%s", str(e), traceback.format_exc())
        return "Booking reminder task failed."


@shared_task
def send_smart_rebooking_prompts():
    """
    Analyzes booking history and sends notifications to users when it's time to rebook.
    """
    # This is a placeholder. You would need to define your own logic for what constitutes
    # a "smart" rebooking prompt (e.g., based on service type, frequency, etc.).
    logger.info("Running smart rebooking prompts task...")
    # Example: Find users who had a booking for a service with a duration of more than 60 minutes
    # and whose last booking was more than 30 days ago.
    thirty_days_ago = timezone.now() - timedelta(days=30)
    bookings_to_prompt = Booking.objects.filter(
        status='completed',
        slot__service__duration__gt=60,
        created_at__lt=thirty_days_ago
    ).distinct('user')

    for booking in bookings_to_prompt:
        notify_user(
            booking.user,
            "It's time to rebook your appointment!",
            f"Ready for your next session of {booking.slot.service.title}? Book now to keep up the great work!",
            data={"service_id": booking.slot.service.id}
        )
    logger.info(f"Sent {bookings_to_prompt.count()} rebooking prompts.")


@shared_task
def send_auto_followups():
    """
    Sends follow-up messages after appointments.
    """
    logger.info("Running auto-followups task...")
    # Example: Send a follow-up 24 hours after a booking is completed.
    twenty_four_hours_ago = timezone.now() - timedelta(hours=24)
    completed_bookings = Booking.objects.filter(
        status='completed',
        updated_at__gte=twenty_four_hours_ago - timedelta(minutes=5),
        updated_at__lt=twenty_four_hours_ago
    )
    for booking in completed_bookings:
        notify_user(
            booking.user,
            "How was your recent appointment?",
            f"We hope you enjoyed your {booking.slot.service.title} at {booking.shop.name}. We'd love to hear your feedback!",
            data={"booking_id": booking.id, "shop_id": booking.shop.id}
        )
    logger.info(f"Sent {completed_bookings.count()} follow-up messages.")


@shared_task
def reengage_ghost_clients():
    """
    Identifies inactive users and sends them targeted promotions to re-engage them.
    """
    logger.info("Running ghost client re-engagement task...")
    # Example: Find users who haven't booked in the last 90 days
    ninety_days_ago = timezone.now() - timedelta(days=90)
    active_users = Booking.objects.filter(
        created_at__gte=ninety_days_ago
    ).values_list('user_id', flat=True)

    ghost_users = User.objects.exclude(id__in=active_users)

    for user in ghost_users:
        notify_user(
            user,
            "We miss you!",
            "It's been a while! Come back and enjoy a 10% discount on your next booking.",
            data={"discount_code": "COMEBACK10"}
        )
    logger.info(f"Sent {ghost_users.count()} re-engagement notifications.")