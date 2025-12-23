"""
Shared timezone utilities for consistent time handling.

V1 Fix Implementation:
- All API responses use UTC with 'Z' suffix
- Clients convert to local using shop_timezone (IANA format)
- Notification cadence uses shop timezone for week/day calculations
"""
import zoneinfo
from datetime import datetime, timezone as dt_tz


def to_utc_iso(dt) -> str | None:
    """
    Convert a datetime to UTC ISO 8601 format with 'Z' suffix.
    Returns None if dt is None.
    
    Use this for ALL API datetime responses to ensure consistency.
    """
    if dt is None:
        return None
    
    if dt.tzinfo is None:
        # Naive datetime - assume UTC
        dt = dt.replace(tzinfo=dt_tz.utc)
    
    utc_dt = dt.astimezone(dt_tz.utc)
    return utc_dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def format_for_display(dt, shop_timezone_str: str) -> str:
    """
    Convert UTC datetime to shop's local time for display.
    Used for email/SMS notifications, NOT API responses.
    
    Args:
        dt: datetime object (should be UTC)
        shop_timezone_str: IANA timezone string (e.g., 'America/New_York')
    
    Returns:
        Formatted string like "Monday, December 23, 2025 at 10:30 AM EST"
    """
    if dt is None:
        return ""
    
    try:
        tz = zoneinfo.ZoneInfo(shop_timezone_str)
    except Exception:
        tz = zoneinfo.ZoneInfo("America/New_York")
    
    local_dt = dt.astimezone(tz)
    return local_dt.strftime("%A, %B %d, %Y at %I:%M %p %Z")


def get_valid_iana_timezone(tz_str: str | None, default: str = "America/New_York") -> str:
    """
    Validate and return an IANA timezone string.
    Falls back to default if invalid or empty.
    
    Args:
        tz_str: Timezone string to validate
        default: Fallback timezone if tz_str is invalid
    
    Returns:
        Valid IANA timezone string
    """
    if not tz_str:
        return default
    
    try:
        zoneinfo.ZoneInfo(tz_str)
        return tz_str
    except Exception:
        return default


def get_shop_local_datetime(shop, utc_dt=None):
    """
    Convert a UTC datetime to the shop's local timezone.
    If utc_dt is None, uses current time.
    
    Args:
        shop: Shop model instance with time_zone field
        utc_dt: Optional UTC datetime (defaults to now)
    
    Returns:
        datetime in shop's local timezone
    """
    if utc_dt is None:
        from django.utils import timezone
        utc_dt = timezone.now()
    
    try:
        shop_tz = zoneinfo.ZoneInfo(shop.time_zone or "America/New_York")
    except Exception:
        shop_tz = zoneinfo.ZoneInfo("America/New_York")
    
    return utc_dt.astimezone(shop_tz)


def get_shop_current_week(shop):
    """
    Get the current ISO week number in the shop's timezone.
    
    Args:
        shop: Shop model instance with time_zone field
    
    Returns:
        tuple (year, week_number)
    """
    local_now = get_shop_local_datetime(shop)
    iso = local_now.isocalendar()
    return (iso[0], iso[1])  # (year, week)


def get_shop_current_date(shop):
    """
    Get today's date in the shop's timezone.
    
    Args:
        shop: Shop model instance with time_zone field
    
    Returns:
        date object
    """
    local_now = get_shop_local_datetime(shop)
    return local_now.date()


def was_sent_this_week(shop, sent_at_utc):
    """
    Check if a notification was sent this week (in shop's timezone).
    
    This is used for notification cadence tracking to prevent
    sending weekly notifications more than once per week.
    
    Args:
        shop: Shop model instance
        sent_at_utc: UTC datetime when notification was sent
    
    Returns:
        bool - True if sent this week
    """
    if sent_at_utc is None:
        return False
    
    current_year, current_week = get_shop_current_week(shop)
    
    # Convert sent_at to shop's timezone to get the week it was sent
    sent_local = get_shop_local_datetime(shop, sent_at_utc)
    sent_iso = sent_local.isocalendar()
    
    return sent_iso[0] == current_year and sent_iso[1] == current_week


def was_sent_today(shop, sent_at_utc):
    """
    Check if a notification was sent today (in shop's timezone).
    
    This is used for daily notification cadence tracking.
    
    Args:
        shop: Shop model instance
        sent_at_utc: UTC datetime when notification was sent
    
    Returns:
        bool - True if sent today
    """
    if sent_at_utc is None:
        return False
    
    today = get_shop_current_date(shop)
    
    # Convert sent_at to shop's timezone to get the date it was sent
    sent_local = get_shop_local_datetime(shop, sent_at_utc)
    
    return sent_local.date() == today
