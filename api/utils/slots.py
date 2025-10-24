# api/utils/slots.py
from django.utils import timezone
from rest_framework.exceptions import ValidationError

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
