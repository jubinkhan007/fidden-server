from celery import shared_task
from django.utils import timezone
from payments.models import Booking

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
