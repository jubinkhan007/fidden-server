from datetime import timedelta, datetime, date
import pytz
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from api.models import (
    Shop, Provider, Service, AvailabilityRuleSet, 
    ProviderDayLock, SlotBooking, Slot, ServiceCategory
)
from subscriptions.models import apply_defaults_on_subscription_change, ShopSubscription
from django.db.models.signals import post_save

User = get_user_model()

class Phase3ConcurrencyTests(TestCase):
    def setUp(self):
        # Mute signal that requires apply_plan_defaults method on Shop
        post_save.disconnect(apply_defaults_on_subscription_change, sender=ShopSubscription)
        
        self.client = APIClient()
        self.user = User.objects.create_user(email="user@example.com", password="password", name="Test User")
        self.other_user = User.objects.create_user(email="other@example.com", password="password", name="Other User")
        self.owner = User.objects.create_user(email="owner@example.com", password="password", name="Owner")
        
        self.shop = Shop.objects.create(
            owner=self.owner,
            name="Test Shop",
            time_zone="UTC",
            use_rule_based_availability=True,
            capacity=5,
            start_at="09:00:00",
            close_at="17:00:00",
            address="123 Test St",
            location="Test City"
        )
        
        # Setup Ruleset
        self.ruleset = AvailabilityRuleSet.objects.create(
            name="Standard",
            timezone="UTC",
            weekly_rules={
                "mon": [["09:00", "17:00"]],
                "tue": [["09:00", "17:00"]],
                "wed": [["09:00", "17:00"]],
                "thu": [["09:00", "17:00"]],
                "fri": [["09:00", "17:00"]],
                "sat": [],
                "sun": []
            }
        )
        # 9-17 Mon-Sun
        # We'll set this up if we need explicit rules, or rely on defaults.
        # Let's set implicit logic or mock working windows if needed.
        # But for integration testing, let's use the actual engine.
        # We need a rule for "today" or the target date.
        # Let's use a fixed date.
        self.target_date = date(2026, 2, 5) # Thursday
        
        # Provider 1
        self.p1 = Provider.objects.create(
            shop=self.shop,
            name="Provider 1",
            availability_ruleset=self.ruleset,
            is_active=True,
            allow_any_provider_booking=True
        )
        # Provider 2
        self.p2 = Provider.objects.create(
            shop=self.shop,
            name="Provider 2",
            availability_ruleset=self.ruleset,
            is_active=True,
            allow_any_provider_booking=True
        )
        
        # Service Category
        self.category = ServiceCategory.objects.create(name="Barber")

        # Service: 30 mins
        self.service = Service.objects.create(
            shop=self.shop,
            category=self.category,
            title="Haircut",
            duration=30,
            price=20.00,
            is_active=True
        )
        self.p1.services.add(self.service)
        self.p2.services.add(self.service)
        
        self.client.force_authenticate(user=self.user)

    def test_provider_day_lock_created(self):
        """Verify that a booking creates a ProviderDayLock."""
        url = "/api/bookings/"
        data = {
            "shop_id": self.shop.id,
            "service_id": self.service.id,
            "start_at": "2026-02-05T10:00:00Z",
            # provider_id is None -> Any Provider
        }
        response = self.client.post(url, data)
        if response.status_code != status.HTTP_201_CREATED:
            print(f"Booking Failed: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Check Lock existence
        lock = ProviderDayLock.objects.filter(shop=self.shop, date=self.target_date).first()
        self.assertIsNotNone(lock) 
        
    def test_double_booking_same_provider_fails(self):
        """
        If Provider 1 is booked at 10:00, a second request for Provider 1 at 10:00 should fail.
        """
        start_at = "2026-02-05T10:00:00Z"
        
        # 1. Book P1 explicitly
        response1 = self.client.post("/api/bookings/", {
            "shop_id": self.shop.id, 
            "service_id": self.service.id, 
            "start_at": start_at, 
            "provider_id": self.p1.id
        })
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)
        
        # 2. Try to book P1 again
        self.client.force_authenticate(user=self.other_user)
        response2 = self.client.post("/api/bookings/", {
            "shop_id": self.shop.id, 
            "service_id": self.service.id, 
            "start_at": start_at, 
            "provider_id": self.p1.id
        })
        self.assertEqual(response2.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response2.data['code'], "NO_PROVIDER_AVAILABLE")

    def test_load_balancing_any_provider(self):
        """
        Request 1: Any -> Assigned to P1 (id 1)
        Request 2: Any -> Should be Assigned to P2 (id 2) because P1 is busy.
        """
        # Ensure IDs are ordered for deterministic test if logic uses ID as tie breaker
        # P1 created first, likely ID smaller.
        
        start_at = "2026-02-05T11:00:00Z"
        
        # Booking 1
        res1 = self.client.post("/api/bookings/", {
            "shop_id": self.shop.id, "service_id": self.service.id, "start_at": start_at
        })
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)
        assigned_p1_name = res1.data['provider_name']
        
        # Booking 2
        self.client.force_authenticate(user=self.other_user)
        res2 = self.client.post("/api/bookings/", {
            "shop_id": self.shop.id, "service_id": self.service.id, "start_at": start_at
        })
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)
        assigned_p2_name = res2.data['provider_name']
        
        self.assertNotEqual(assigned_p1_name, assigned_p2_name)
        
    def test_processing_overlap_concurrency(self):
        """
        Service allows processing overlap.
        Duration: 60 mins.
        Provider Block: 15 mins (processing starts at 15m).
        Processing Window: 45 mins.
        
        Time 0: Book P1. Blocked 0-15. Processing 15-60.
        Time 15: Should be bookable! (Blocked 15-30).
        """
        # Update service to allow processing overlap
        self.service.allow_processing_overlap = True
        self.service.duration = 60
        # Processing window = Duration (60) - Block (X). Wanted 45 mins processing -> Block = 15.
        self.service.provider_block_minutes = 15 
        self.service.save()
        
        start_1 = "2026-02-05T12:00:00Z" # 12:00 - 13:00. P-Block: 12:00-12:15.
        
        # Book 1
        res1 = self.client.post("/api/bookings/", {
            "shop_id": self.shop.id, "service_id": self.service.id, "start_at": start_1,
            "provider_id": self.p1.id
        })
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)
        
        # Attempt to book at 12:15
        # P1 is "Processing" from 12:15 to 13:00.
        # New Booking starts 12:15. P-Block 12:15-12:30.
        # Overlap Check:
        # Existing Busy: 12:00-12:15.
        # New P-Block: 12:15-12:30. No overlap with existing busy.
        # 2. Concurrency Check:
        # We need to ensure provider has capacity for concurrent jobs.
        self.p1.max_concurrent_processing_jobs = 5
        self.p1.save()
        
        start_2 = "2026-02-05T12:15:00Z"
        self.client.force_authenticate(user=self.other_user)
        res2 = self.client.post("/api/bookings/", {
            "shop_id": self.shop.id, "service_id": self.service.id, "start_at": start_2,
            "provider_id": self.p1.id
        })
        
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED, "Should allow booking during processing window")

    def test_conflict_return_shape(self):
        """Verify the 409 response has code and detail."""
        # Book P1
        start_at = "2026-02-05T14:00:00Z"
        self.client.post("/api/bookings/", {
            "shop_id": self.shop.id, "service_id": self.service.id, "start_at": start_at, "provider_id": self.p1.id
        })
        
        # Book P1 again
        res = self.client.post("/api/bookings/", {
            "shop_id": self.shop.id, "service_id": self.service.id, "start_at": start_at, "provider_id": self.p1.id
        })
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertIn('code', res.data)
        self.assertEqual(res.data['code'], 'NO_PROVIDER_AVAILABLE')
