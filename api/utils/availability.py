import logging
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta, time, date
from typing import List, Tuple, Optional, Dict, NamedTuple
from django.utils import timezone
from api.models import (
    Provider, AvailabilityRuleSet, AvailabilityException, 
    Shop, Service, ProviderDayLock
)
from payments.models import Booking

logger = logging.getLogger(__name__)

# ==========================================
# 1. Primitives & Helpers
# ==========================================

class Interval(NamedTuple):
    start: datetime
    end: datetime

class BlockedInterval(NamedTuple):
    start: datetime
    end: datetime
    is_busy: bool  # True = busy (hard), False = processing (soft/concurrent)
    booking_id: Optional[int] = None

def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """
    Check if two half-open intervals [a_start, a_end) and [b_start, b_end) overlap.
    Overlap exists if a_start < b_end AND b_start < a_end.
    """
    return a_start < b_end and b_start < a_end

def ceil_to_interval(minutes_from_midnight: int, interval_minutes: int) -> int:
    """
    Round up minutes-from-midnight to the next multiple of interval_minutes.
    Example: 545 (9:05), interval=15 -> 555 (9:15). 540 (9:00) -> 540.
    """
    if interval_minutes <= 0:
        return minutes_from_midnight
    
    remainder = minutes_from_midnight % interval_minutes
    if remainder == 0:
        return minutes_from_midnight
    return minutes_from_midnight + (interval_minutes - remainder)

def get_tz_aware_dt(date_obj: date, time_obj: time, tz: ZoneInfo) -> datetime:
    """Create a timezone-aware datetime from date, time, and timezone."""
    dt = datetime.combine(date_obj, time_obj)
    if timezone.is_aware(dt):
        return dt.astimezone(tz)
    return dt.replace(tzinfo=tz)

def to_utc(dt: datetime) -> datetime:
    """Convert aware datetime to UTC."""
    return dt.astimezone(ZoneInfo('UTC'))

def is_valid_iana_timezone(tz_id: str) -> bool:
    """Check if a timezone ID is valid IANA."""
    try:
        ZoneInfo(tz_id)
        return True
    except Exception:
        return False

def resolve_timezone_id(provider: Provider) -> str:
    """
    Resolve the IANA timezone ID for a provider.
    Priority: Provider Ruleset -> Shop Default Ruleset -> Shop.time_zone -> Fallback
    """
    if provider.availability_ruleset and provider.availability_ruleset.timezone:
        return provider.availability_ruleset.timezone
    
    shop = provider.shop
    if shop.default_availability_ruleset and shop.default_availability_ruleset.timezone:
        return shop.default_availability_ruleset.timezone
    
    if shop.time_zone:
        return shop.time_zone
    
    return 'America/New_York'  # Fallback

def safe_localize(date_obj: date, time_str: str, tz_id: str) -> Optional[datetime]:
    """
    Safely create a timezone-aware datetime from date + "HH:MM" string.
    
    Uses the minute-offset approach for DST safety:
    - Returns aware datetime if the local wall time exists
    - Returns None if time doesn't exist (spring-forward gap)
    
    For ambiguous times (fall-back), uses fold=0 (first occurrence).
    """
    try:
        tz = ZoneInfo(tz_id)
        t = datetime.strptime(time_str, "%H:%M").time()
        dt_naive = datetime.combine(date_obj, t)
        
        # Create aware datetime with fold=0 (first occurrence for ambiguous times)
        dt_aware = dt_naive.replace(tzinfo=tz, fold=0)
        
        # Round-trip check: Convert to UTC and back to local
        utc_dt = dt_aware.astimezone(ZoneInfo('UTC'))
        round_trip = utc_dt.astimezone(tz)
        
        # If the wall time differs after round-trip, this time doesn't exist
        if round_trip.hour != dt_aware.hour or round_trip.minute != dt_aware.minute:
            return None
        
        return dt_aware
    except Exception as e:
        logger.error(f"safe_localize error: {e} for {date_obj} {time_str} {tz_id}")
        return None

def safe_localize_minutes(date_obj: date, minutes_from_midnight: int, tz_id: str) -> Optional[datetime]:
    """
    Safely create a timezone-aware datetime from date + minutes-from-midnight.
    This is the preferred method for grid iteration to avoid DST drift.
    """
    hours = minutes_from_midnight // 60
    mins = minutes_from_midnight % 60
    
    # Validate time bounds
    if hours >= 24 or hours < 0 or mins < 0 or mins >= 60:
        return None
    
    time_str = f"{hours:02d}:{mins:02d}"
    return safe_localize(date_obj, time_str, tz_id)


# ==========================================
# 2. Working Window Resolution
# ==========================================

def get_working_windows(provider: Provider, date_obj: date) -> List[Interval]:
    """
    Determine the base working hours for a provider on a specific date.
    Priority: Exception > Provider Ruleset > Shop Default Ruleset > Shop Business Hours (Legacy)
    Returns list of Intervals in provider's timezone/UTC.
    """
    # 0. Check Exception
    exception = AvailabilityException.objects.filter(provider=provider, date=date_obj).first()
    if exception:
        if exception.is_closed:
            return []
        if exception.override_rules:
            # Format: [["09:00", "12:00"], ...]
            return _parse_rules(exception.override_rules, date_obj, provider.shop.time_zone)
    
    # 1. Check Provider Ruleset
    ruleset = provider.availability_ruleset
    if ruleset:
        return _get_ruleset_intervals(ruleset, date_obj)
        
    # 2. Check Shop Default Ruleset
    shop = provider.shop
    if shop.default_availability_ruleset:
        return _get_ruleset_intervals(shop.default_availability_ruleset, date_obj)
        
    # 3. Fallback to Legacy Shop Business Hours
    return _get_legacy_shop_intervals(shop, date_obj)

def get_breaks(provider: Provider, date_obj: date) -> List[Interval]:
    """
    Get break intervals.
    Priority: Exception > Ruleset > Shop Breaks
    """
    # 0. Exception
    exception = AvailabilityException.objects.filter(provider=provider, date=date_obj).first()
    if exception and exception.override_breaks:
         # Assuming override_breaks format similar to ruleset but simpler? 
         # Or just [["12:00", "13:00"]]?
         # Spec implementation_plan.md says: [{"start": "12:00", "end": "13:00", "days": [...]}] typically
         # But exceptions might just be timebox list. Let's assume list of objects for consistency or simple list.
         # For simplicity in this engine logic, we'll parse standard break objects.
         return _parse_break_objects(exception.override_breaks, date_obj, provider.shop.time_zone)

    # 1. Provider Ruleset
    ruleset = provider.availability_ruleset
    if ruleset:
        return _get_ruleset_breaks(ruleset, date_obj)
        
    # 2. Shop Default Ruleset
    shop = provider.shop
    if shop.default_availability_ruleset:
        return _get_ruleset_breaks(shop.default_availability_ruleset, date_obj)

    # 3. Legacy Shop Breaks
    # Shop model: break_start_time, break_end_time (daily recurrence)
    if shop.break_start_time and shop.break_end_time:
         # Legacy: use shop timezone
         tz = ZoneInfo(shop.time_zone)
         start_dt = get_tz_aware_dt(date_obj, shop.break_start_time, tz)
         end_dt = get_tz_aware_dt(date_obj, shop.break_end_time, tz)
         if start_dt < end_dt:
             return [Interval(start_dt, end_dt)]
             
    return []

def _get_ruleset_intervals(ruleset: AvailabilityRuleSet, date_obj: date) -> List[Interval]:
    """Get working intervals from a ruleset for a specific weekday."""
    day_key = date_obj.strftime("%a").lower() # 'mon', 'tue'...
    rules = ruleset.weekly_rules.get(day_key, [])
    if not rules:
        return []
        
    # ZoneInfo cache optimization not needed here as _parse_rules takes str
    return _parse_rules(rules, date_obj, ruleset.timezone)

def _get_ruleset_breaks(ruleset: AvailabilityRuleSet, date_obj: date) -> List[Interval]:
    """Get breaks from ruleset."""
    day_key = date_obj.strftime("%a").lower()
    day_breaks = []
    
    # Breaks format: [{"start": "12:00", "end": "13:00", "days": ["mon", "tue"]}]
    for b in ruleset.breaks:
        if day_key in b.get('days', []):
            day_breaks.append(b)
            
    return _parse_break_objects(day_breaks, date_obj, ruleset.timezone)

def _parse_rules(rules_list: List[List[str]], date_obj: date, tz_name: str) -> List[Interval]:
    """Parse list of [start_str, end_str] into Intervals using DST-safe localization."""
    intervals = []
    
    for r in rules_list:
        if len(r) != 2: 
            continue
        try:
            start_dt = safe_localize(date_obj, r[0], tz_name)
            end_dt = safe_localize(date_obj, r[1], tz_name)
            
            # Skip if either time doesn't exist (spring-forward gap)
            if start_dt is None or end_dt is None:
                logger.warning(f"Skipping rule {r} on {date_obj} - time doesn't exist (DST gap)")
                continue
            
            if start_dt < end_dt:
                intervals.append(Interval(start_dt, end_dt))
        except ValueError:
            logger.error(f"Invalid time format in rules: {r}")
            continue
            
    return intervals

def _parse_break_objects(break_objs: List[Dict], date_obj: date, tz_name: str) -> List[Interval]:
    """Parse break objects into Intervals using DST-safe localization."""
    intervals = []
    
    for b in break_objs:
        try:
            start_dt = safe_localize(date_obj, b['start'], tz_name)
            end_dt = safe_localize(date_obj, b['end'], tz_name)
            
            # Skip if either time doesn't exist (spring-forward gap)
            if start_dt is None or end_dt is None:
                continue
            
            if start_dt < end_dt:
                intervals.append(Interval(start_dt, end_dt))
        except (ValueError, KeyError):
            continue
    return intervals

def _get_legacy_shop_intervals(shop: Shop, date_obj: date) -> List[Interval]:
    """Use legacy Shop business_hours JSON."""
    day_key = date_obj.strftime("%a").lower()
    # Format: {"mon": [["09:00", "17:00"]]} or if overrides exist
    # Fallback to start_at/close_at if not in business_hours
    
    intervals = []
    # If using rulesets, timezone is stored on ruleset or shop
    # We need to localize the current time to check "now"
    
    # Use helper
    tz_id = resolve_timezone_id(provider)
    tz = ZoneInfo(tz_id)
    
    # Check overrides/custom hours first
    if shop.business_hours and day_key in shop.business_hours:
         # Assuming same [["HH:MM", "HH:MM"]] format as new rules
         return _parse_rules(shop.business_hours[day_key], date_obj, shop.time_zone)
         
    # Fallback to general start/close
    # Check close_days
    if day_key in shop.close_days:
        return []
        
    if shop.start_at and shop.close_at:
        start_dt = get_tz_aware_dt(date_obj, shop.start_at, tz)
        end_dt = get_tz_aware_dt(date_obj, shop.close_at, tz)
        if start_dt < end_dt:
            intervals.append(Interval(start_dt, end_dt))
            
    return intervals


# ==========================================
# 3. Blocked Intervals
# ==========================================

def get_blocked_intervals(provider: Provider, date_obj: date) -> Tuple[List[BlockedInterval], List[BlockedInterval]]:
    """
    Get all blocking intervals for a provider on a date.
    Returns (busy_blocks, processing_blocks).
    
    busy_blocks: Hard conflicts (Breaks + Booking.busy_interval)
    processing_blocks: Concurrent conflicts (Booking.processing_window)
    """
    tz_name = provider.availability_ruleset.timezone if provider.availability_ruleset else provider.shop.time_zone
    tz = ZoneInfo(tz_name)
    
    busy_blocks = []
    processing_blocks = []
    
    # 1. Add Breaks as Busy Blocks
    breaks = get_breaks(provider, date_obj)
    for b in breaks:
        busy_blocks.append(BlockedInterval(b.start, b.end, is_busy=True, booking_id=None))
        
    # 2. Add Bookings (Legacy Booking Model)
    # We need bookings that overlap the target DATE
    day_start = get_tz_aware_dt(date_obj, time.min, tz)
    day_end = get_tz_aware_dt(date_obj, time.max, tz)
    
    bookings = Booking.objects.filter(
        provider=provider,
        status__in=['active', 'confirmed'], # Exclude cancelled/no-show
        total_end__gt=day_start,
        provider_busy_start__lt=day_end
    )
    
    for b in bookings:
        # Hard Busy Block
        if b.provider_busy_start and b.provider_busy_end:
            busy_blocks.append(BlockedInterval(
                b.provider_busy_start,
                b.provider_busy_end,
                is_busy=True,
                booking_id=b.id
            ))
            
        # Processing Block (if exists)
        if b.processing_start and b.processing_end:
            processing_blocks.append(BlockedInterval(
                b.processing_start,
                b.processing_end,
                is_busy=False,
                booking_id=b.id
            ))
            
    # 3. Add SlotBookings (New Model - Rule-based)
    # These might rely on dynamic connection to Service for buffers
    from api.models import SlotBooking
    
    slot_bookings = SlotBooking.objects.filter(
        provider=provider,
        status__in=['confirmed', 'pending'],
        end_time__gt=day_start,
        start_time__lt=day_end
    ).select_related('service')
    
    for sb in slot_bookings:
        svc = sb.service
        s_start = sb.start_time
        s_end = sb.end_time # (start + duration)
        
        # Calculate Buffers dynamically
        buffer_before = timedelta(minutes=svc.buffer_before_minutes)
        buffer_after = timedelta(minutes=svc.buffer_after_minutes)
        prov_block_mins = svc.effective_provider_block_minutes
        
        # Busy Block: [Start - BufferBefore, Start + ProviderBlock]
        # BUT if ProviderBlock < Duration (Processing), we have a split.
        # If ProviderBlock == Duration, then Busy is [Start - Buffer, End + BufferAfter]
        
        busy_start = s_start - buffer_before
        
        if svc.allow_processing_overlap and svc.processing_window_minutes > 0:
            # Complex Case: Processing Enabled
            # Busy: [Start - Buffer, Start + ProvBlock]
            # Processing: [Start + ProvBlock, Start + Duration]
            # Cleanup (BufferAfter): [Start + Duration, Start + Duration + BufferAfter]
            # Usually cleanup requires provider, so it's BUSY.
            
            busy_end_1 = s_start + timedelta(minutes=prov_block_mins)
            
            # Add Initial Busy Block
            busy_blocks.append(BlockedInterval(busy_start, busy_end_1, is_busy=True, booking_id=sb.id))
            
            # Add Processing Block
            proc_start = busy_end_1
            proc_end = s_end # (Start + Duration)
            if proc_start < proc_end:
                 processing_blocks.append(BlockedInterval(proc_start, proc_end, is_busy=False, booking_id=sb.id))
            
            # Add Cleanup Busy Block (if any)
            if svc.buffer_after_minutes > 0:
                cleanup_start = s_end
                cleanup_end = s_end + buffer_after
                busy_blocks.append(BlockedInterval(cleanup_start, cleanup_end, is_busy=True, booking_id=sb.id))
                
        else:
            # Simple Case: Full Duration is Busy
            # Busy: [Start - Buffer, End + BufferAfter]
            busy_end = s_end + buffer_after
            busy_blocks.append(BlockedInterval(busy_start, busy_end, is_busy=True, booking_id=sb.id))

    return busy_blocks, processing_blocks


# ==========================================
# 4. Provider Available Starts
# ==========================================

def provider_available_starts(
    provider: Provider, 
    service: Service, 
    date_obj: date
) -> List[datetime]:
    """
    Calculate all valid start times for a service with a provider on a date.
    
    DST-Safe Algorithm:
    - Generate candidate wall-times using minute offsets (not timedelta on aware datetimes)
    - Localize each candidate independently using safe_localize_minutes()
    - Skip non-existent times (spring-forward gaps)
    - Convert to UTC for conflict checks
    
    Enforces rules:
    1. Must fit in Working Window (considering total duration + buffers)
    2. Must not overlap Busy Blocks (provider_busy_minutes)
    3. Processing concurrency limit (if enabled)
    """
    
    # 0. Setup
    tz_id = resolve_timezone_id(provider)
    
    # Grid interval
    interval_minutes = provider.shop.default_interval_minutes
    if provider.availability_ruleset:
        interval_minutes = provider.availability_ruleset.interval_minutes
        
    start_time_limit = timezone.now()  # Don't return past slots
    
    # Get configuration
    windows = get_working_windows(provider, date_obj)
    busy_blocks, processing_blocks = get_blocked_intervals(provider, date_obj)
    
    available_slots = []
    
    # Pre-calculate service duration offsets (in minutes)
    buffer_before_mins = service.buffer_before_minutes
    provider_block_mins = service.effective_provider_block_minutes
    duration_mins = service.duration or 0
    buffer_after_mins = service.buffer_after_minutes
    total_service_mins = duration_mins + buffer_after_mins
    
    # Convert windows to minute ranges for iteration
    for window in windows:
        # Convert window boundaries to minutes-from-midnight in LOCAL time
        window_start_mins = window.start.hour * 60 + window.start.minute
        window_end_mins = window.end.hour * 60 + window.end.minute
        
        # Align to grid
        current_mins = ceil_to_interval(window_start_mins, interval_minutes)
        
        # Iterate using minute offsets (DST-safe)
        while current_mins < window_end_mins:
            # 1. Localize candidate time (may return None for DST gaps)
            candidate_local = safe_localize_minutes(date_obj, current_mins, tz_id)
            
            if candidate_local is None:
                # Time doesn't exist (spring-forward gap) - skip
                current_mins += interval_minutes
                continue
            
            # 2. Past check
            if candidate_local <= start_time_limit:
                current_mins += interval_minutes
                continue
            
            # 3. Fit in Window Check
            # End of service must fit within window
            end_mins = current_mins + total_service_mins
            if end_mins > window_end_mins:
                # Doesn't fit, exit this window
                break
            
            # 4. Convert to UTC for conflict checks (all conflict checks in UTC)
            candidate_utc = to_utc(candidate_local)
            
            # Calculate busy interval in UTC
            cand_busy_start = candidate_utc - timedelta(minutes=buffer_before_mins)
            cand_busy_end = candidate_utc + timedelta(minutes=provider_block_mins)
            
            # 5. Busy Overlap Check
            is_busy_conflict = False
            for bb in busy_blocks:
                bb_start_utc = to_utc(bb.start) if bb.start.tzinfo else bb.start
                bb_end_utc = to_utc(bb.end) if bb.end.tzinfo else bb.end
                if overlaps(cand_busy_start, cand_busy_end, bb_start_utc, bb_end_utc):
                    is_busy_conflict = True
                    break
            
            if is_busy_conflict:
                current_mins += interval_minutes
                continue
                
            # 6. Concurrency Check (if applicable)
            if service.allow_processing_overlap and service.processing_window_minutes > 0:
                cand_proc_start = cand_busy_end
                cand_proc_end = candidate_utc + timedelta(minutes=duration_mins)
                
                concurrent_count = 0
                for pb in processing_blocks:
                    pb_start_utc = to_utc(pb.start) if pb.start.tzinfo else pb.start
                    pb_end_utc = to_utc(pb.end) if pb.end.tzinfo else pb.end
                    if overlaps(cand_proc_start, cand_proc_end, pb_start_utc, pb_end_utc):
                        concurrent_count += 1
                
                if concurrent_count >= provider.max_concurrent_processing_jobs:
                    current_mins += interval_minutes
                    continue
            
            # 7. Valid Slot - store the LOCAL aware datetime
            available_slots.append(candidate_local)
            current_mins += interval_minutes
            
    return available_slots


# ==========================================
# 5. Any Provider Selection
# ==========================================

def get_any_provider_availability(
    shop: Shop, 
    service: Service, 
    date_obj: date
) -> List[Dict]:
    """
    Aggregate availability for "Any Provider".
    Returns list of {"start_time": dt, "available_count": int}
    """
    providers = Provider.objects.filter(
        shop=shop, 
        services=service, 
        is_active=True, 
        allow_any_provider_booking=True
    )
    
    # Map start_time -> count
    availability_map = {}
    
    for p in providers:
        slots = provider_available_starts(p, service, date_obj)
        for s in slots:
            if s not in availability_map:
                availability_map[s] = 0
            availability_map[s] += 1
            
    # Convert to sorted list
    result = []
    for dt in sorted(availability_map.keys()):
        result.append({
            "start_time": dt,
            "available_count": availability_map[dt]
        })
    return result

def select_best_provider(
    shop: Shop, 
    service: Service, 
    date_obj: date, 
    start_time: datetime
) -> Optional[Provider]:
    """
    Select the best provider for a given slot using workload balancing.
    Primary: Fewest bookings on that date.
    Secondary: Lowest ID (Deterministic).
    """
    
    # 1. Identify Valid Candidates (who are actually free at this time)
    candidates = Provider.objects.filter(
        shop=shop, 
        services=service, 
        is_active=True, 
        allow_any_provider_booking=True
    )
    
    valid_candidates = []
    for p in candidates:
        # Check specific availability for this single time
        # TODO: Optimize? Calling full provider_available_starts might be heavy.
        # But for Phase 1/2 robustness, reuse the trusted function.
        # Check if start_time is in the returned list.
        # Optimization: We can write a boolean `is_provider_available(p, s, t)` later.
        
        # Quick check:
        # To reuse logic without full generation:
        # But `provider_available_starts` is the Source of Truth.
        # For a single point check, calculating the whole day is slightly inefficient but safe.
        # Given "Phase 2", let's be safe.
        
        slots = provider_available_starts(p, service, date_obj)
        if start_time in slots:
             # Calculate score: Workload
             # Count bookings on this date (simple day workload)
             # Better: Count bookings that OVERLAP this specific service? 
             # User spec: "bookins overlapping that date" (simplest workload metric)
             
             workload = Booking.objects.filter(
                 provider=p, 
                 slot__start_time__date=date_obj, # Assuming SlotBooking still has start_time or use Booking fields
                 status__in=['active', 'confirmed']
             ).count()
             
             valid_candidates.append((workload, p.id, p))
             
    if not valid_candidates:
        return None
        
    # Sort: Workload ASC, ID ASC
    valid_candidates.sort(key=lambda x: (x[0], x[1]))
    
    return valid_candidates[0][2]

def get_ranked_providers(
    shop: Shop, 
    service: Service, 
    date_obj: date, 
    start_time: datetime
) -> List[Provider]:
    """
    Get list of valid providers sorted by best match (workload, ID).
    Used for 'Any Provider' retry logic.
    """
    candidates = Provider.objects.filter(
        shop=shop, 
        services=service, 
        is_active=True, 
        allow_any_provider_booking=True
    )
    
    valid_candidates = []
    for p in candidates:
        workload = Booking.objects.filter(
            provider=p, 
            slot__start_time__date=date_obj,
            status__in=['active', 'confirmed']
        ).count()
        valid_candidates.append((workload, p.id, p))
        
    # Sort: Workload ASC, ID ASC
    valid_candidates.sort(key=lambda x: (x[0], x[1]))
    
    return [c[2] for c in valid_candidates]
