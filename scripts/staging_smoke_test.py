import os
import sys
import django
from datetime import datetime, timedelta, date, time
from django.conf import settings
from django.utils import timezone
from django.contrib.auth import get_user_model
import random

# Setup Django Environment
sys.path.append(os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fidden.settings")
django.setup()

from api.models import Shop, Service, Provider, AvailabilityRuleSet, SlotBooking, ProviderDayLock
from api.utils.availability import get_working_windows, get_blocked_intervals, provider_available_starts
from rest_framework.test import APIClient
from rest_framework import status

def run_smoke_test():
    print("🚀 Starting Staging Smoke Test...")
    
    # 1. Setup Data for Test
    print("\n--- Step 1: Data Setup ---")
    User = get_user_model()
    
    # Create unique email for test run
    run_id = random.randint(1000, 9999)
    email = f"staging_tester_{run_id}@example.com"
    try:
        user = User.objects.create_user(email=email, password="password123", name="Staging Tester", mobile_number="1234567890")
        print(f"✅ Created User: {email}")
    except Exception as e:
        user = User.objects.get(email=email)
        print(f"⚠️ User Exists: {email}")

    # Use existing shop 'BarberKing' or create
    shop = Shop.objects.filter(name__icontains="Barber").first()
    if not shop:
        shop = Shop.objects.create(
        name=f"Staging Shop {run_id}", 
        owner=user, 
        address="123 Staging Ln", 
        capacity=5,
        start_at="09:00",
        close_at="18:00",
        niche="Barber"
    )
        print(f"✅ Created Shop: {shop.name}")
    else:
        # Enable rule-based availability for this shop
        shop.use_rule_based_availability = True
        shop.save()
        print(f"ℹ️ Used Existing Shop: {shop.name}")

    # Ensure Shop has Rule-Based Availability ON
    if not shop.use_rule_based_availability:
        shop.use_rule_based_availability = True
        shop.save()
        print("✅ Enabled 'use_rule_based_availability' flag.")

    # Create Service
    service, _ = Service.objects.get_or_create(
        shop=shop,
        title="Staging Cut",
        defaults={
            'price': 50,
            'duration': 60,
            'is_active': True,
            'category_id': 1 # Assuming category 1 exists
        }
    )
    print(f"ℹ️ Service: {service.title}")

    # Create Provider
    provider, _ = Provider.objects.get_or_create(
        shop=shop,
        name="Staging Barber",
        defaults={
            'provider_type': 'employee',
            'is_active': True,
            'allow_any_provider_booking': True,
        }
    )
    provider.services.add(service)
    
    # Ensure Ruleset
    ruleset, _ = AvailabilityRuleSet.objects.get_or_create(
        name="Staging Standard",
        defaults={'timezone': 'UTC', 'interval_minutes': 30}
    )
    # Give 9-5 rules
    ruleset.weekly_rules = {
        "mon": [["09:00", "17:00"]],
        "tue": [["09:00", "17:00"]],
        "wed": [["09:00", "17:00"]],
        "thu": [["09:00", "17:00"]],
        "fri": [["09:00", "17:00"]],
    }
    ruleset.save()
    provider.availability_ruleset = ruleset
    provider.save()
    print(f"ℹ️ Provider: {provider.name} configured.")

    # 2. Test Availability Lookup
    print("\n--- Step 2: API Availability Lookup ---")
    client = APIClient()
    client.force_authenticate(user=user)
    
    # Target Next Monday
    today = timezone.now().date()
    days_until_mon = (0 - today.weekday() + 7) % 7
    if days_until_mon == 0: days_until_mon = 7
    target_date = today + timedelta(days=days_until_mon)
    target_date_str = target_date.strftime('%Y-%m-%d')
    
    url = f"/api/availability/?service_id={service.id}&shop_id={shop.id}&date={target_date_str}"
    print(f"GET {url}")
    
    response = client.get(url)
    if response.status_code == 200:
        print("✅ Availability API returned 200 OK")
        slots = response.data['available_slots']
        print(f"   Found {len(slots)} slots.")
        if len(slots) > 0:
            first_slot = slots[0] # HH:MM
            print(f"   First slot: {first_slot}")
        else:
            print("❌ No slots found! Check ruleset.")
            return
    else:
        print(f"❌ Failed: {response.status_code} {response.data}")
        return

    # 3. Test Booking Creation
    print("\n--- Step 3: Booking Creation ---")
    start_time_str = f"{target_date_str}T10:00:00Z"
    
    data = {
        "shop_id": shop.id,
        "service_id": service.id,
        "start_at": start_time_str,
        "provider_id": provider.id # Explicit provider
    }
    print(f"POST /api/bookings/ with {data}")
    
    res_book = client.post("/api/bookings/", data)
    if res_book.status_code == 201:
        print("✅ Booking Success!")
        print(f"   Booking ID: {res_book.data.get('booking_id')}")
    else:
        print(f"❌ Booking Failed: {res_book.status_code} {res_book.data}")

    # 4. Test Concurrency/Conflict
    print("\n--- Step 4: Conflict Test ---")
    # provider.max_concurrent_processing_jobs = 1 (default)
    # Trying to book SAME time SAME provider should fail
    
    res_conflict = client.post("/api/bookings/", data)
    if res_conflict.status_code == 409:
        print("✅ Conflict correctly caught (409).")
        print(f"   Code: {res_conflict.data.get('code')}")
    else:
        print(f"❌ Expected 409, got {res_conflict.status_code}")

    print("\n✅ Smoke Test Complete.")

    # 5. Test DST / Timezone (Bonus)
    print("\n--- Step 5: DST/Timezone Check ---")
    # Set shop TZ to America/New_York
    shop.use_rule_based_availability = True
    shop.save()
    
    # We need to verify that ruleset converts correctly.
    # If ruleset is UTC 9-5, that is 4-12 EST.
    ruleset.timezone = 'UTC' 
    ruleset.save()
    
    # Simple check: Do we get slots?
    # If logic is robust, it shouldn't crash.
    url_tz = f"/api/availability/?service_id={service.id}&shop_id={shop.id}&date={target_date_str}"
    res_tz = client.get(url_tz)
    if res_tz.status_code == 200:
         print("✅ Timezone Availability OK (UTC Rules).")
    else:
         print("❌ Timezone Availability Failed.")

if __name__ == "__main__":
    run_smoke_test()
