import logging
import pytz
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

def ceil_to_interval(dt: datetime, interval_minutes: int) -> datetime:
    """
    Round up datetime to the next multiple of interval_minutes.
    Example: 9:05, interval=15 -> 9:15. 9:00 -> 9:00.
    """
    if interval_minutes <= 0:
        return dt
    
    delta = timedelta(minutes=interval_minutes)
    # Start of day (arbitrary anchor)
    anchor = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    
    diff = dt - anchor
    minutes = diff.total_seconds() / 60
    remainder = minutes % interval_minutes
    
    if remainder == 0:
        return dt.replace(second=0, microsecond=0)
        
    minutes_to_add = interval_minutes - remainder
    return (dt + timedelta(minutes=minutes_to_add)).replace(second=0, microsecond=0)

def to_utc(dt: datetime) -> datetime:
    """Convert aware datetime to UTC."""
    return dt.astimezone(timezone.utc)

def get_tz_aware_dt(d: date, t: time, tz: timezone.tzinfo) -> datetime:
    """Combine date and time in a specific timezone."""
    dt = datetime.combine(d, t)
    return timezone.make_aware(dt, tz)

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
         tz = pytz.timezone(shop.time_zone)
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
        
    tz = pytz.timezone(ruleset.timezone)
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
    """Parse list of [start_str, end_str] into Intervals."""
    intervals = []
    tz = pytz.timezone(tz_name)
    
    for r in rules_list:
        if len(r) != 2: continue
        try:
            start_t = datetime.strptime(r[0], "%H:%M").time()
            end_t = datetime.strptime(r[1], "%H:%M").time()
            
            start_dt = get_tz_aware_dt(date_obj, start_t, tz)
            end_dt = get_tz_aware_dt(date_obj, end_t, tz)
            
            if start_dt < end_dt:
                intervals.append(Interval(start_dt, end_dt))
        except ValueError:
            logger.error(f"Invalid time format in rules: {r}")
            continue
            
    return intervals

def _parse_break_objects(break_objs: List[Dict], date_obj: date, tz_name: str) -> List[Interval]:
    intervals = []
    tz = pytz.timezone(tz_name)
    
    for b in break_objs:
        try:
            start_t = datetime.strptime(b['start'], "%H:%M").time()
            end_t = datetime.strptime(b['end'], "%H:%M").time()
            
            start_dt = get_tz_aware_dt(date_obj, start_t, tz)
            end_dt = get_tz_aware_dt(date_obj, end_t, tz)
            
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
    tz = pytz.timezone(shop.time_zone)
    
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
    tz = pytz.timezone(tz_name)
    
    busy_blocks = []
    processing_blocks = []
    
    # 1. Add Breaks as Busy Blocks
    breaks = get_breaks(provider, date_obj)
    for b in breaks:
        busy_blocks.append(BlockedInterval(b.start, b.end, is_busy=True, booking_id=None))
        
    # 2. Add Bookings (Optimized Query)
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
    Enforces rules:
    1. Must fit in Working Window (considering total duration + buffers)
    2. Must not overlap Busy Blocks (provider_busy_minutes)
    3. Processing concurrency limit (if enabled)
    """
    
    # 0. Setup
    tz_name = provider.availability_ruleset.timezone if provider.availability_ruleset else provider.shop.time_zone
    tz = pytz.timezone(tz_name)
    
    # Grid interval
    interval_minutes = provider.shop.default_interval_minutes
    if provider.availability_ruleset:
        interval_minutes = provider.availability_ruleset.interval_minutes
        
    start_time_limit = timezone.now() # Don't return past slots
    
    # Get configuration
    windows = get_working_windows(provider, date_obj)
    busy_blocks, processing_blocks = get_blocked_intervals(provider, date_obj)
    
    available_slots = []
    
    # Pre-calculate service intervals relative to 't'
    # busy: [t - buffer_before, t + provider_block]
    # processing: [t + provider_block, t + duration]
    # total_end: t + duration + buffer_after
    
    buffer_before = timedelta(minutes=service.buffer_before_minutes)
    provider_block = timedelta(minutes=service.effective_provider_block_minutes)
    total_processing_end = timedelta(minutes=(service.duration or 0)) # duration relative to t
    buffer_after_td = timedelta(minutes=service.buffer_after_minutes) # distinct from buffer_before variable
    
    # Loop each working window
    for window in windows:
        # Align window start to grid
        current_t = ceil_to_interval(window.start, interval_minutes)
        window_end = window.end
        
        while current_t < window_end:
            # 1. Past check
            if current_t <= start_time_limit:
                current_t += timedelta(minutes=interval_minutes)
                continue
                
            # 2. Fit in Window Check (Rule 3)
            # End of service activity (including buffer after) must fall within window
            # Actually, usually buffers imply provider presence.
            # If buffer_after is "cleanup", it must be inside window? Usually yes.
            # Let's assume total_end must be <= window_end
            
            service_end_time = current_t + timedelta(minutes=(service.duration or 0)) + buffer_after_td
            if service_end_time > window_end:
                # Optimized exit: if this t doesn't fit, later t won't fit this window
                break
                
            # 3. Construct Candidate Intervals
            cand_busy_start = current_t - buffer_before
            cand_busy_end = current_t + provider_block
            
            # Rule 1: Busy Overlap Check
            is_busy_conflict = False
            for bb in busy_blocks:
                if overlaps(cand_busy_start, cand_busy_end, bb.start, bb.end):
                    is_busy_conflict = True
                    break
            
            if is_busy_conflict:
                current_t += timedelta(minutes=interval_minutes)
                continue
                
            # Rule 2: Concurrency Check (if applicable)
            if service.allow_processing_overlap and service.processing_window_minutes > 0:
                cand_proc_start = cand_busy_end
                cand_proc_end = current_t + timedelta(minutes=(service.duration or 0))
                
                concurrent_count = 0
                for pb in processing_blocks:
                    if overlaps(cand_proc_start, cand_proc_end, pb.start, pb.end):
                        concurrent_count += 1
                
                if concurrent_count >= provider.max_concurrent_processing_jobs:
                    # Concurrency limit hit
                    current_t += timedelta(minutes=interval_minutes)
                    continue
            
            # 4. Valid Slot
            available_slots.append(current_t)
            current_t += timedelta(minutes=interval_minutes)
            
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
