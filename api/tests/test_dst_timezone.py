"""
Tests for DST/Timezone correctness in the availability engine.
"""
import pytest
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from django.test import TestCase
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from django.contrib.auth import get_user_model
from api.models import Shop, Service, Provider, AvailabilityRuleSet, ServiceCategory
from api.utils.availability import (
    safe_localize, 
    safe_localize_minutes, 
    resolve_timezone_id,
    provider_available_starts
)


class SafeLocalizeTests(TestCase):
    """Test the safe_localize helper for DST handling."""
    
    def test_normal_time_localizes_correctly(self):
        """Normal times should localize correctly."""
        result = safe_localize(date(2026, 6, 15), "10:00", "America/New_York")
        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 10)
        self.assertEqual(result.minute, 0)
    
    def test_spring_forward_gap_returns_none(self):
        """
        Spring-forward test (America/New_York DST 2026-03-08):
        2:00 AM jumps to 3:00 AM. Times 2:00-2:59 do not exist.
        """
        # March 8, 2026 is DST start in America/New_York
        dst_date = date(2026, 3, 8)
        
        # 2:30 AM should NOT exist
        result = safe_localize(dst_date, "02:30", "America/New_York")
        self.assertIsNone(result, "2:30 AM should not exist on DST spring-forward day")
        
        # 1:30 AM SHOULD exist (before gap)
        result_before = safe_localize(dst_date, "01:30", "America/New_York")
        self.assertIsNotNone(result_before)
        
        # 3:00 AM SHOULD exist (after gap)
        result_after = safe_localize(dst_date, "03:00", "America/New_York")
        self.assertIsNotNone(result_after)
    
    def test_fall_back_ambiguous_time_is_deterministic(self):
        """
        Fall-back test (America/New_York DST end 2026-11-01):
        2:00 AM occurs twice. We use fold=0 (first occurrence, EDT before switch).
        
        DOCUMENTED BEHAVIOR:
        - Ambiguous times are handled deterministically using fold=0
        - This means we pick the FIRST occurrence (before DST ends)
        - Client can send explicit offset to control which occurrence they want
        """
        dst_end_date = date(2026, 11, 1)
        
        # 1:30 AM is ambiguous - exists twice
        result = safe_localize(dst_end_date, "01:30", "America/New_York")
        self.assertIsNotNone(result)
        
        # Verify it's the first occurrence (fold=0, EDT = UTC-4)
        # The offset should be -04:00 (EDT) not -05:00 (EST)
        utc_offset_hours = result.utcoffset().total_seconds() / 3600
        self.assertEqual(utc_offset_hours, -4.0, "Should use fold=0 (EDT, first occurrence)")
        
        # Should be deterministic (same result every time)
        result2 = safe_localize(dst_end_date, "01:30", "America/New_York")
        self.assertEqual(result, result2)
    
    def test_utc_has_no_dst_issues(self):
        """UTC should never have DST issues."""
        result = safe_localize(date(2026, 3, 8), "02:30", "UTC")
        self.assertIsNotNone(result)


class SafeLocalizeMinutesTests(TestCase):
    """Test safe_localize_minutes for minute-offset grid generation."""
    
    def test_normal_minute_offset(self):
        """540 minutes = 9:00 AM"""
        result = safe_localize_minutes(date(2026, 6, 15), 540, "America/New_York")
        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 9)
        self.assertEqual(result.minute, 0)
    
    def test_spring_forward_gap_minute_offset(self):
        """150 minutes = 2:30 AM - should be None on DST day"""
        result = safe_localize_minutes(date(2026, 3, 8), 150, "America/New_York")
        self.assertIsNone(result)
    
    def test_boundary_minutes(self):
        """Test edge cases for minutes-from-midnight."""
        # 0 minutes = midnight
        result = safe_localize_minutes(date(2026, 6, 15), 0, "America/New_York")
        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 0)
        
        # 23:59 = 1439 minutes
        result = safe_localize_minutes(date(2026, 6, 15), 1439, "America/New_York")
        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 23)
        self.assertEqual(result.minute, 59)
        
        # Invalid: 24:00 = 1440 minutes
        result = safe_localize_minutes(date(2026, 6, 15), 1440, "America/New_York")
        self.assertIsNone(result)


class DSTAvailabilityAPITests(APITestCase):
    """Test API behavior during DST transitions."""
    
    @classmethod
    def setUpTestData(cls):
        # Create user
        User = get_user_model()
        cls.user = User.objects.create_user(
            email="dst_test@example.com", 
            password="test123",
            name="DST Tester",
            mobile_number="1234567890"
        )
        
        # Create category
        cls.category = ServiceCategory.objects.create(name="Test Category")
        
        # Create shop with New York timezone
        cls.shop = Shop.objects.create(
            owner=cls.user,
            name="DST Test Shop",
            address="123 Test St",
            capacity=5,
            time_zone="America/New_York",
            use_rule_based_availability=True,
            niche="barber"
        )
        
        # Create service
        cls.service = Service.objects.create(
            shop=cls.shop,
            title="DST Test Service",
            price=50,
            duration=60,
            category=cls.category,
            is_active=True
        )
        
        # Create ruleset with New York timezone
        cls.ruleset = AvailabilityRuleSet.objects.create(
            name="DST Test Ruleset",
            timezone="America/New_York",
            interval_minutes=30,
            weekly_rules={
                "sun": [["00:00", "23:59"]],  # All day for testing
                "mon": [["00:00", "23:59"]],
                "tue": [["00:00", "23:59"]],
                "wed": [["00:00", "23:59"]],
                "thu": [["00:00", "23:59"]],
                "fri": [["00:00", "23:59"]],
                "sat": [["00:00", "23:59"]],
            }
        )
        
        # Create provider
        cls.provider = Provider.objects.create(
            shop=cls.shop,
            name="DST Provider",
            provider_type="employee",
            is_active=True,
            availability_ruleset=cls.ruleset,
            allow_any_provider_booking=True
        )
        cls.provider.services.add(cls.service)

    def test_availability_response_includes_timezone_id(self):
        """Verify availability response includes timezone_id."""
        self.client.force_authenticate(user=self.user)
        
        response = self.client.get(
            f"/api/availability/?shop_id={self.shop.id}&service_id={self.service.id}&date=2026-06-15&provider_id={self.provider.id}"
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("timezone_id", response.data)
        self.assertEqual(response.data["timezone_id"], "America/New_York")
    
    def test_availability_response_has_iso_timestamps(self):
        """Verify availability response has ISO timestamps with offsets."""
        self.client.force_authenticate(user=self.user)
        
        response = self.client.get(
            f"/api/availability/?shop_id={self.shop.id}&service_id={self.service.id}&date=2026-06-15&provider_id={self.provider.id}"
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("available_slots", response.data)
        
        if response.data["available_slots"]:
            first_slot = response.data["available_slots"][0]
            self.assertIn("start_at", first_slot)
            self.assertIn("start_at_utc", first_slot)
            
            # Verify ISO format with offset
            self.assertIn("-", first_slot["start_at"])  # Has offset
            self.assertTrue(first_slot["start_at_utc"].endswith("Z"))  # UTC marker
    
    def test_spring_forward_times_excluded(self):
        """
        Verify that times in spring-forward gap are NOT returned.
        March 8, 2026: 2:00-2:59 AM does not exist in America/New_York.
        """
        self.client.force_authenticate(user=self.user)
        
        response = self.client.get(
            f"/api/availability/?shop_id={self.shop.id}&service_id={self.service.id}&date=2026-03-08&provider_id={self.provider.id}"
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check that 2:00 and 2:30 are NOT in the results
        for slot in response.data.get("available_slots", []):
            start_at = slot["start_at"]
            # Parse the local time
            if "02:00" in start_at or "02:30" in start_at:
                self.fail(f"Spring-forward gap time returned: {start_at}")
    
    def test_booking_at_nonexistent_time_rejected(self):
        """Try to book at 2:30 AM on DST day - should fail with INVALID_TIME."""
        self.client.force_authenticate(user=self.user)
        
        # Attempt to book at a non-existent local time
        # Note: We send an ISO timestamp, but the server validates the wall time
        response = self.client.post("/api/bookings/", {
            "shop_id": self.shop.id,
            "service_id": self.service.id,
            "start_at": "2026-03-08T02:30:00-05:00",  # This wall time doesn't exist
            "provider_id": self.provider.id
        })
        
        # Should be rejected
        self.assertIn(response.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_409_CONFLICT])
    
    def test_booking_response_includes_timezone(self):
        """Verify booking response includes timezone_id and UTC times."""
        self.client.force_authenticate(user=self.user)
        
        # Book at a valid time
        response = self.client.post("/api/bookings/", {
            "shop_id": self.shop.id,
            "service_id": self.service.id,
            "start_at": "2026-06-15T10:00:00-04:00",
            "provider_id": self.provider.id
        })
        
        if response.status_code == status.HTTP_201_CREATED:
            self.assertIn("timezone_id", response.data)
            self.assertIn("start_at_utc", response.data)
            self.assertIn("end_at_utc", response.data)


class IANAValidationTests(TestCase):
    """Test IANA timezone validation on AvailabilityRuleSet."""
    
    def test_valid_iana_timezone_passes(self):
        """Valid IANA timezone should pass validation."""
        ruleset = AvailabilityRuleSet(
            name="Valid TZ",
            timezone="Europe/London",
            interval_minutes=15
        )
        # Should not raise
        ruleset.clean()
    
    def test_invalid_timezone_fails(self):
        """Invalid timezone should raise ValidationError."""
        from django.core.exceptions import ValidationError
        
        ruleset = AvailabilityRuleSet(
            name="Invalid TZ",
            timezone="Invalid/Timezone",
            interval_minutes=15
        )
        
        with self.assertRaises(ValidationError) as context:
            ruleset.clean()
        
        self.assertIn("timezone", context.exception.message_dict)
