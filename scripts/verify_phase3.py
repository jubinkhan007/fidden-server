import os
import sys
import django
# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime, date, timedelta
import pytz

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fidden.settings')
django.setup()

from django.utils import timezone
from django.db.models.signals import post_save, pre_save, post_delete, pre_delete
from api.models import Shop, Provider, Service, ServiceCategory, AvailabilityRuleSet, Slot
from rest_framework.test import APIRequestFactory, force_authenticate
from api.availability_views import AvailabilityView, BookingCreateView
from django.contrib.auth import get_user_model

User = get_user_model()

class MuteSignals:
    def __init__(self, signals=None):
        self.signals = signals or [post_save, pre_save, post_delete, pre_delete]
        self.paused_receivers = []

    def __enter__(self):
        for signal in self.signals:
            self.paused_receivers.append((signal, signal.receivers))
            signal.receivers = []

    def __exit__(self, exc_type, exc_val, exc_tb):
        for signal, receivers in self.paused_receivers:
            signal.receivers = receivers

def setup_test_data():
    print("Setting up test data...")
    with MuteSignals():
        # Clean up
        User.objects.filter(email__in=["testuser@example.com", "owner3@example.com"]).delete()
        Shop.objects.filter(name="Phase 3 Shop").delete()

        user = User.objects.create_user(email="testuser@example.com", password="password", name="Test User")
        owner = User.objects.create_user(email="owner3@example.com", password="password", name="Owner 3")
        
        shop = Shop.objects.create(
            owner=owner,
            name="Phase 3 Shop",
            address="123 Phase 3 St",
            capacity=5,
            start_at="09:00",
            close_at="17:00",
            time_zone="UTC",
            use_rule_based_availability=True,
            niche="Barber"
        )

    ruleset = AvailabilityRuleSet.objects.create(
        name="Standard 9-5",
        timezone="UTC",
        weekly_rules={
            "mon": [["09:00", "17:00"]],
            "tue": [["09:00", "17:00"]],
            "wed": [["09:00", "17:00"]],
            "thu": [["09:00", "17:00"]],
            "fri": [["09:00", "17:00"]]
        }
    )

    provider = Provider.objects.create(
        shop=shop,
        name="Provider 1",
        availability_ruleset=ruleset,
        is_active=True
    )

    cat = ServiceCategory.objects.get_or_create(name="Haircut")[0]
    service = Service.objects.create(
        shop=shop,
        category=cat,
        title="Quick Cut",
        price=30,
        duration=30,
        is_active=True
    )
    provider.services.add(service)

    return user, shop, service, provider

def verify_phase3():
    user, shop, service, provider = setup_test_data()
    factory = APIRequestFactory()

    # 1. Test AvailabilityView
    print("\n--- Testing AvailabilityView ---")
    target_date = (date.today() + timedelta(days=1))
    if target_date.weekday() >= 5: # Weekend shift to Monday
        target_date += timedelta(days=(7 - target_date.weekday()))
    
    date_str = target_date.strftime("%Y-%m-%d")
    view = AvailabilityView.as_view()
    
    request = factory.get(f'/api/availability/?shop_id={shop.id}&service_id={service.id}&date={date_str}')
    response = view(request)
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.data}")
    
    if response.status_code == 200:
        print("✅ Availability retrieval successful")
    else:
        print("❌ Availability retrieval failed")

    # 2. Test BookingCreateView (Mock flow)
    print("\n--- Testing BookingCreateView ---")
    view_booking = BookingCreateView.as_view()
    
    # We choose 09:00
    start_at = datetime.combine(target_date, datetime.strptime("09:00", "%H:%M").time())
    start_at = pytz.UTC.localize(start_at)
    
    payload = {
        "shop_id": shop.id,
        "service_id": service.id,
        "start_at": start_at.isoformat()
    }
    
    request = factory.post('/api/bookings/', payload, format='json')
    force_authenticate(request, user=user)
    
    try:
        response = view_booking(request)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.data}")
        
        if response.status_code == 200:
            print("✅ Booking creation (initial phase) successful")
        else:
            print(f"❌ Booking creation failed: {response.data}")
    except Exception as e:
        print(f"❌ Booking creation crashed: {e}")

if __name__ == "__main__":
    verify_phase3()
