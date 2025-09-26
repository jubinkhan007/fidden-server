from celery import shared_task
from django.utils import timezone
from datetime import timedelta
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


