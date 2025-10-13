# api/tasks.py
import logging
from datetime import datetime, timedelta
from django.utils import timezone
from django.conf import settings
from celery import shared_task
from django.core.mail import send_mail
from django.db.models import Count, Avg, Sum
from payments.models import Booking
from .models import PerformanceAnalytics, Slot, SlotBooking, Shop
from api import models

logger = logging.getLogger(__name__)

def _aware(dt):
    """Ensure datetime is timezone-aware."""
    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt


@shared_task
def calculate_analytics():
    for shop in Shop.objects.all():
        bookings = Booking.objects.filter(shop=shop)
        total_bookings = bookings.count()

        # Basic Analytics
        total_revenue = shop.revenues.aggregate(total=Sum('revenue'))['total'] or 0 # Use Sum directly
        average_rating = shop.ratings.aggregate(avg=Avg('rating'))['avg'] or 0.0

        # Moderate Analytics
        cancellation_rate = (bookings.filter(status='cancelled').count() / total_bookings * 100) if total_bookings > 0 else 0

        # Advanced Analytics
        repeat_customer_rate = 0
        if total_bookings > 0:
            customer_counts = bookings.values('user').annotate(count=Count('id'))
            repeat_customers = sum(1 for c in customer_counts if c['count'] > 1)
            total_customers = len(customer_counts)
            repeat_customer_rate = (repeat_customers / total_customers * 100) if total_customers > 0 else 0

        top_service = bookings.values('slot__service__title').annotate(count=Count('id')).order_by('-count').first()
        peak_booking_time = bookings.values('slot__start_time__hour').annotate(count=Count('id')).order_by('-count').first()

        PerformanceAnalytics.objects.update_or_create(
            shop=shop,
            defaults={
                'total_revenue': total_revenue,
                'total_bookings': total_bookings,
                'average_rating': average_rating,
                'cancellation_rate': cancellation_rate,
                'repeat_customer_rate': repeat_customer_rate,
                'top_service': top_service['slot__service__title'] if top_service else None,
                'peak_booking_time': f"{peak_booking_time['slot__start_time__hour']}:00" if peak_booking_time else None,
            }
        )


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def prefill_slots(self, days_ahead=14):
    """
    Prefill slots for the next `days_ahead` days per shop/service.
    - Idempotent: fills missing slots instead of skipping whole days
    - Handles cross-month continuous slot creation
    - Always ensures coverage for `days_ahead` days from today
    """
    created_count = 0
    try:
        # --- CLEAN PREVIOUS / PAST SLOTS ---
        past_slots = Slot.objects.filter(end_time__lt=timezone.now()).filter(bookings__isnull=True)
        deleted_count, _ = past_slots.delete()
        if deleted_count:
            logger.info(f"[Prefill Slots] Deleted {deleted_count} past slots (without bookings).")

        # --- CREATE NEW SLOTS ---
        today = timezone.localdate()
        target_end = today + timedelta(days=days_ahead - 1)

        for shop in Shop.objects.prefetch_related("services").all():
            services = shop.services.filter(is_active=True)
            for service in services:
                start_date = today  # FIX: Always start from today
                end_date = target_end

                for offset in range((end_date - start_date).days + 1):
                    date = start_date + timedelta(days=offset)
                    weekday = date.strftime("%A").lower()

                    if (shop.close_days or []) and weekday in shop.close_days:
                        continue

                    duration = service.duration or 30
                    start_dt = timezone.make_aware(datetime.combine(date, shop.start_at), timezone.get_current_timezone())
                    end_dt = timezone.make_aware(datetime.combine(date, shop.close_at), timezone.get_current_timezone())
                    if end_dt <= start_dt:
                        continue

                    # Get existing start times for this shop/service/date
                    existing_times = set(
                        Slot.objects.filter(shop=shop, service=service, start_time__date=date)
                        .values_list("start_time", flat=True)
                    )

                    current = start_dt
                    batch = []
                    while current + timedelta(minutes=duration) <= end_dt:
                        if current not in existing_times:  # only add missing slots
                            batch.append(Slot(
                                shop=shop,
                                service=service,
                                start_time=current,
                                end_time=current + timedelta(minutes=duration),
                                capacity_left=service.capacity,
                            ))
                        current += timedelta(minutes=duration)

                    if batch:
                        Slot.objects.bulk_create(batch, ignore_conflicts=True)
                        created_count += len(batch)
                        logger.info(f"[Prefill Slots] Created {len(batch)} slots for {shop.name} / {service.title} on {date}")

        logger.info(f"[Prefill Slots] Created {created_count} slots across all shops/services.")
        return f"Prefilled {days_ahead} days with {created_count} slots."

    except Exception as e:
        logger.error(f"[Prefill Slots] Error: {e}", exc_info=True)
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def send_upcoming_slot_reminders(self, window_minutes=30):
    """Send reminders for upcoming confirmed bookings."""
    now = timezone.now()
    window_end = now + timedelta(minutes=window_minutes)
    try:
        upcoming = SlotBooking.objects.select_related("user", "service", "shop")\
            .filter(status="confirmed", start_time__gte=now, start_time__lte=window_end)
        sent_count = 0
        for b in upcoming:
            email = getattr(b.user, "email", None)
            if not email:
                continue
            subject = f"Reminder: {b.service.title} at {b.shop.name}"
            msg = f"Dear {b.user.username},\n\nYour booking for {b.service.title} " \
                  f"starts at {timezone.localtime(b.start_time).strftime('%Y-%m-%d %H:%M')}.\n\nThank you!"
            try:
                send_mail(subject, msg, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
                sent_count += 1
            except Exception as e:
                logger.warning(f"[Reminder] Failed to send to {email}: {e}")
        logger.info(f"[Reminder] Sent {sent_count} reminders for upcoming slots.")
        return f"Sent {sent_count} reminders."
    except Exception as e:
        logger.error(f"[Reminder Task] Error: {e}", exc_info=True)
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def cleanup_old_cancelled_bookings(self, days=7, batch_size=1000):
    """Cleanup old cancelled bookings, restore slot capacity."""
    try:
        cutoff = timezone.now() - timedelta(days=days)
        total_deleted = 0
        while True:
            old_bookings = SlotBooking.objects.select_for_update()\
                .filter(status="cancelled", start_time__lt=cutoff).order_by("id")[:batch_size]
            if not old_bookings.exists():
                break
            for booking in old_bookings:
                slot = booking.slot
                slot.capacity_left += 1
                slot.save(update_fields=['capacity_left'])
                booking.delete()
                total_deleted += 1
            if old_bookings.count() < batch_size:
                break
        logger.info(f"[Cleanup] Deleted {total_deleted} old cancelled bookings (older than {days} days).")
        return f"Deleted {total_deleted} old cancelled bookings."
    except Exception as e:
        logger.error(f"[Cleanup Task] Error: {e}", exc_info=True)
        raise self.retry(exc=e)

@shared_task
def auto_cancel_booking(booking_id):
    try:
        booking = SlotBooking.objects.select_related("slot", "shop").get(id=booking_id)
    except SlotBooking.DoesNotExist:
        logger.warning(f"Booking {booking_id} does not exist.")
        return f"Booking {booking_id} does not exist."

    if booking.payment_status == "pending" and booking.status != "cancelled":
        booking.status = "cancelled"
        booking.save(update_fields=["status"])
        logger.info(f"Booking {booking_id} auto-cancelled due to payment timeout.")

        if booking.slot.capacity_left is not None:
            booking.slot.capacity_left += 1
            booking.slot.save(update_fields=["capacity_left"])

        if booking.shop.capacity is not None:
            booking.shop.capacity += 1
            booking.shop.save(update_fields=["capacity"])

        return f"Booking {booking_id} auto-cancelled."

    logger.info(f"Booking {booking_id} not cancelled (already paid or cancelled).")
    return f"Booking {booking_id} not cancelled."