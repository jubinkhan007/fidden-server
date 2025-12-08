# api/utils/slots.py
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from datetime import datetime, timedelta
from django.utils import timezone
from api.models import Slot

def assert_slot_bookable(slot, *, grace_minutes: int = 0):
    """
    Raises ValidationError if slot is not bookable:
    - start_time must be in the future (optionally allow a small grace)
    - capacity_left > 0
    """
    if not slot:
        raise ValidationError("Slot not found.")
    now = timezone.now()
    cutoff = now if grace_minutes <= 0 else now - timezone.timedelta(minutes=grace_minutes)
    if not slot.start_time:
        raise ValidationError("Slot has no start time.")
    if slot.start_time <= cutoff:
        raise ValidationError("This slot has already started or passed.")
    if (slot.capacity_left or 0) <= 0:
        raise ValidationError("This slot is full.")
    

def generate_slots_for_service(service, *, days_ahead=14, start_date=None):
    """
    Create time-slots for a single service from start_date for days_ahead.
    Uses shop.get_intervals_for_date (same as prefill_slots).
    Idempotent: skips existing Slot.start_time values.
    
    IMPORTANT: Uses shop.time_zone to correctly interpret working hours.
    """
    import zoneinfo
    
    shop = service.shop

    if start_date is None:
        start_date = timezone.localdate()

    target_end = start_date + timedelta(days=days_ahead - 1)
    duration = service.duration or 30
    
    # Get shop's timezone (default to America/New_York if not set)
    try:
        shop_tz = zoneinfo.ZoneInfo(shop.time_zone or "America/New_York")
    except Exception:
        shop_tz = zoneinfo.ZoneInfo("America/New_York")

    for offset in range((target_end - start_date).days + 1):
        date = start_date + timedelta(days=offset)

        # Respect close_days via existing helper
        intervals = shop.get_intervals_for_date(date)
        if not intervals:
            continue

        # Existing slots for this service on that date
        existing_times = set(
            Slot.objects.filter(
                shop=shop,
                service=service,
                start_time__date=date
            ).values_list("start_time", flat=True)
        )

        batch = []
        for (start_t, end_t) in intervals:
            # Combine date + time in shop's local timezone, then convert to aware datetime
            naive_start = datetime.combine(date, start_t)
            naive_end = datetime.combine(date, end_t)
            
            # Make aware using shop's timezone (this is the key fix!)
            start_dt = naive_start.replace(tzinfo=shop_tz)
            end_dt = naive_end.replace(tzinfo=shop_tz)
            
            if end_dt <= start_dt:
                continue

            current = start_dt
            while current + timedelta(minutes=duration) <= end_dt:
                # avoid slots in the past for "today"
                if current <= timezone.now():
                    current += timedelta(minutes=duration)
                    continue

                if current not in existing_times:
                    batch.append(Slot(
                        shop=shop,
                        service=service,
                        start_time=current,
                        end_time=current + timedelta(minutes=duration),
                        capacity_left=service.capacity,
                    ))
                current += timedelta(minutes=duration)

        if batch:
            # ignore_conflicts in case unique constraints exist
            Slot.objects.bulk_create(batch, ignore_conflicts=True)

def regenerate_service_slots(service, *, days_ahead=14):
    """
    Regenerate slots for a specific service, preserving existing bookings.
    1. Find future slots for this service.
    2. Delete those that are NOT booked.
    3. Call generate_slots_for_service to recreate them with new settings (duration/price).
    """
    from api.models import Slot
    
    # 1. Identify future slots
    now = timezone.now()
    future_slots = Slot.objects.filter(
        service=service,
        start_time__gte=now
    )

    # 2. Delete unbooked slots
    # We keep slots that have any related bookings
    # related_name='bookings' on Slot model
    slots_to_delete = future_slots.filter(bookings__isnull=True)
    count, _ = slots_to_delete.delete()
    
    # 3. Regenerate
    # We use the service's current duration/settings
    generate_slots_for_service(service, days_ahead=days_ahead)
    
    return count

def regenerate_slots_for_shop(shop, *, days_ahead=14, start_date=None):
    """
    Regenerates slots for all active services in a shop.
    1. Deletes FUTURE, UNBOOKED slots for this shop.
    2. Calls generate_slots_for_service for each active service.
    
    This ensures that when shop hours change, the available slots reflect the new schedule immediately.
    Existing bookings are PRESERVED (we only delete slots where bookings__isnull=True).
    """
    if start_date is None:
        start_date = timezone.localdate()

    # 1. Delete unbooked future slots
    # We use 'now' for the safety check to avoid deleting slots that might have just passed but were unbooked
    # However, standard practice is usually to clear from 'start_date' onwards.
    # Let's use start_date converted to datetime for the query to be safe.
    
    # Actually, to be very precise, we should only delete slots that start AFTER now,
    # because we don't want to mess with history or slots happening right this second.
    now = timezone.now()
    
    # Delete unbooked slots for this shop that are in the future
    Slot.objects.filter(
        shop=shop,
        start_time__gte=now,
        bookings__isnull=True
    ).delete()

    # 2. Re-generate for all active services
    active_services = shop.services.filter(is_active=True)
    for service in active_services:
        generate_slots_for_service(service, days_ahead=days_ahead, start_date=start_date)
