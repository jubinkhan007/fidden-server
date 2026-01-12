import os
import django
import sys
from datetime import date, time, datetime, timedelta
import pytz

# Setup Django
sys.path.append(os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fidden.settings")
django.setup()

from api.models import Shop, Service, Provider, AvailabilityRuleSet, AvailabilityException
from payments.models import Booking, SlotBooking
from api.utils.availability import (
    get_working_windows, 
    get_blocked_intervals, 
    provider_available_starts,
    get_any_provider_availability,
    select_best_provider
)
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models.signals import post_save, pre_save

User = get_user_model()

def setup_test_data():
    print("--- Setting up Test Data ---")
    
    # Nuke all signals for this script
    post_save.receivers = []
    pre_save.receivers = []
    
    # 1. User & Shop
    print("Getting/Creating Owner...")
    owner, _ = User.objects.get_or_create(email="phase2@test.com", defaults={'role': 'owner'})
    print("Getting/Creating Shop...")
    shop, created = Shop.objects.get_or_create(
        owner=owner, 
        name="Phase2 Shop", 
        defaults={
            'capacity': 5, # Required field
            'default_interval_minutes': 30, # Grid 30m
            'time_zone': 'America/New_York',
            'start_at': time(9, 0),
            'close_at': time(17, 0),
            'location': "Test Loc",
            'address': "Test Addr",
            'niche': "Barber"
        }
    )
    print("Getting/Creating Ruleset...")
    
    # 2. Ruleset (9-5 Mon)
    ruleset, _ = AvailabilityRuleSet.objects.get_or_create(
        name="Standard 9-5",
        defaults={
            'timezone': 'America/New_York',
            'interval_minutes': 30,
            'weekly_rules': {
                'mon': [["09:00", "17:00"]]
            },
            'breaks': [
                {"start": "12:00", "end": "12:30", "days": ["mon"]}
            ]
        }
    )
    print("Getting/Creating Provider...")
    
    # 3. Provider
    provider, _ = Provider.objects.get_or_create(
        shop=shop, 
        name="Test Provider", 
        defaults={
            'availability_ruleset': ruleset,
            'max_concurrent_processing_jobs': 2
        }
    )
    print("Getting/Creating Category...")
    
    # 4. Service (Hair Color: 90m total, 30m busy, 60m processing)
    # Allows overlap
    from api.models import ServiceCategory
    cat, _ = ServiceCategory.objects.get_or_create(name="TestCat")
    print("Getting/Creating Service...")
    
    service, _ = Service.objects.get_or_create(
        shop=shop,
        title="Color Processing",
        defaults={
            'category': cat,
            'price': 100,
            'duration': 90,
            'provider_block_minutes': 30,
            'allow_processing_overlap': True,
            'buffer_before_minutes': 0,
            'buffer_after_minutes': 0
        }
    )
    
    # 5. Create a Booking to test conflict
    # Booking from 10:00 -> 11:30 (Busy: 10:00-10:30, Proc: 10:30-11:30)
    # We need a date that is a Monday. Let's pick next Mon.
    today = date.today()
    days_ahead = (7 - today.weekday() + 0) % 7 # Next Mon (0)
    if days_ahead == 0: days_ahead = 7
    target_date = today + timedelta(days=days_ahead)
    
    start_time = timezone.make_aware(datetime.combine(target_date, time(10, 0)), pytz.timezone('America/New_York'))
    
    print("Getting/Creating Slot...")
    # Create dummy slot
    from api.models import Slot
    dummy_slot, _ = Slot.objects.get_or_create(
        shop=shop,
        service=service,
        start_time=start_time,
        defaults={
            'end_time': start_time + timedelta(minutes=90),
            'capacity_left': 0
        }
    )
    
    print("Getting/Creating SlotBooking...")
    # Create SlotBooking (Booking.slot points to THIS, not Slot)
    dummy_slot_booking, _ = SlotBooking.objects.get_or_create(
        slot=dummy_slot,
        defaults={
            'user': owner, 
            'shop': shop,
            'service': service,
            'start_time': start_time,
            'end_time': start_time + timedelta(minutes=90),
            'status': 'confirmed'
        }
    )

    print("Getting/Creating Payment...")
    from payments.models import Payment
    dummy_payment, _ = Payment.objects.get_or_create(
        booking=dummy_slot_booking,
        defaults={
            'user': owner,
            'amount': 100.00,
            'is_deposit': False,
            'status': 'succeeded'
        }
    )

    print("Checking Booking...")
    booking_check = Booking.objects.filter(provider=provider, provider_busy_start=start_time).first()
    if not booking_check:
        print("Creating Booking (manual base save)...")
        b = Booking(
            provider=provider,
            slot=dummy_slot_booking,
            payment=dummy_payment, 
            user=owner,
            shop=shop,
            status='confirmed',
            provider_busy_start=start_time,
            provider_busy_end=start_time + timedelta(minutes=30),
            processing_start=start_time + timedelta(minutes=30),
            processing_end=start_time + timedelta(minutes=90),
            total_end=start_time + timedelta(minutes=90),
            created_at=timezone.now(),
            updated_at=timezone.now()
        )
        b.save_base(raw=True)
        pass
    print("Setup done.")
        
    return provider, service, target_date

def run_verification():
    provider, service, target_date = setup_test_data()
    print(f"\n--- Verifying for {provider.name} on {target_date} ---")
    
    # Step 1: Working Windows
    windows = get_working_windows(provider, target_date)
    print("\n1. Working Windows:")
    for w in windows:
        print(f"   {w.start.strftime('%H:%M')} - {w.end.strftime('%H:%M')}")
        
    # Step 2: Blocked Intervals
    busy, processing = get_blocked_intervals(provider, target_date)
    print("\n2. Busy Blocks (Hard):")
    for b in busy:
        print(f"   {b.start.strftime('%H:%M')} - {b.end.strftime('%H:%M')} (Booking: {b.booking_id})")
        
    print("\n3. Processing Blocks (Soft, Concurrent):")
    for p in processing:
        print(f"   {p.start.strftime('%H:%M')} - {p.end.strftime('%H:%M')} (Booking: {p.booking_id})")
        
    # Step 3: Available Starts
    print("\n4. Available Start Times (First 10):")
    slots = provider_available_starts(provider, service, target_date)
    for s in slots[:10]:
        print(f"   {s.strftime('%H:%M')}")
        
    # Analysis
    # Expect: 
    # 9:00 -> OK
    # 9:30 -> OK (Busy 10:00-10:30, but 9:30 + 30m busy = 10:00 end. fits)
    # 10:00 -> BLOCKED (Busy 10:00-10:30)
    # 10:30 -> OK (Processing 10:30-11:30 count=1 < max=2. Busy 10:30-11:00 free)
    # ...
    
    if not slots:
        print("NO SLOTS FOUND!")

if __name__ == "__main__":
    run_verification()
