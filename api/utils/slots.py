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
    """
    shop = service.shop

    if start_date is None:
        start_date = timezone.localdate()

    target_end = start_date + timedelta(days=days_ahead - 1)
    duration = service.duration or 30

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
            start_dt = timezone.make_aware(datetime.combine(date, start_t))
            end_dt = timezone.make_aware(datetime.combine(date, end_t))
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
