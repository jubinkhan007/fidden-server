from django.test import TestCase
from django.utils import timezone
from datetime import timedelta, time, date
from api.models import Shop, Service, Provider, AvailabilityRuleSet, ProviderDayLock
from payments.models import Booking, SlotBooking, Payment
# Need to mock or create dependencies for Shop/Booking (e.g. User, Slot)
from django.contrib.auth import get_user_model
from api.models import ServiceCategory

User = get_user_model()

class Phase1ModelTestCase(TestCase):
    def setUp(self):
        # Basics
        # User model uses email as USERNAME_FIELD, no username field exists
        self.user = User.objects.create_user(email='test@test.com', password='password', role='user', name='Test User')
        self.owner = User.objects.create_user(email='owner@test.com', password='password', role='owner', name='Owner User')
        self.shop = Shop.objects.create(
            owner=self.owner,
            name="Test Shop",
            capacity=5,
            start_at=time(9,0),
            close_at=time(18,0),
            default_interval_minutes=15
        )
        self.category = ServiceCategory.objects.create(name="Test Cat")
        
    def test_service_validation(self):
        """Test Service model clean() method and computed properties"""
        # Case 1: Valid Service
        s = Service.objects.create(
            shop=self.shop,
            category=self.category,
            title="Hair Color",
            price=100.0,
            duration=90,
            provider_block_minutes=30,
            allow_processing_overlap=True,
            buffer_before_minutes=0,
            buffer_after_minutes=10
        )
        
        self.assertEqual(s.effective_provider_block_minutes, 30)
        self.assertEqual(s.processing_window_minutes, 60)
        self.assertEqual(s.total_duration_minutes, 100) # 90 + 0 + 10
        
        # Case 2: Invalid (Block > Duration)
        s_invalid = Service(
            shop=self.shop,
            category=self.category,
            title="Impossible Service",
            price=10.0,
            duration=30,
            provider_block_minutes=40 
        )
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            s_invalid.clean()

    def test_booking_autofields(self):
        """Test Booking model auto-calculation of busy/processing windows"""
        # Setup Service
        service = Service.objects.create(
            shop=self.shop,
            category=self.category,
            title="Complex Service",
            price=100.0,
            duration=60, # 1 hour total
            provider_block_minutes=20, # 20 mins busy
            allow_processing_overlap=True,
            buffer_before_minutes=15, # 15 mins buffer
            buffer_after_minutes=5            
        )
        
        provider = Provider.objects.create(shop=self.shop, name="Jane", user=self.owner)
        
        # Create dependencies for Booking (SlotBooking, Payment)
        # Note: SlotBooking usually created via a Slot, mocking minimal needed
        # We need a SlotBooking with a start_time
        now = timezone.now().replace(second=0, microsecond=0)
        start_time = now + timedelta(hours=1) # Start at T+60m
        
        # Mocking SlotBooking structure roughly
        # This part depends on existing models I haven't seen fully, but assuming standard FKs
        # Need to create Slot first? Or can I mock SlotBooking?
        # Looking at models.py, SlotBooking needs 'slot' which needs 'shop'/'service'
        
        # NOTE: Bypassing complex Slot setup for unit test if possible, but Booking.save() relies on self.slot.service and self.slot.start_time
        
        # Create a dummy object to mimic SlotBooking behavior if models are tight, 
        # but better to try creating real ones.
        # Assuming `api.models.Slot` exists and has `start_time`
        from api.models import Slot
        slot = Slot.objects.create(
            shop=self.shop,
            service=service,
            start_time=start_time,
            end_time=start_time + timedelta(minutes=service.duration),
            capacity=1
        )
        
        slot_booking = SlotBooking.objects.create(
            user=self.user,
            shop=self.shop,
            service=service,
            slot=slot,
            start_time=start_time,
            end_time=start_time + timedelta(minutes=service.duration),
            status="confirmed"
        )
        
        payment = Payment.objects.create(
            booking=slot_booking,
            user=self.user,
            amount=100.0
        )
        
        # Act: Create Booking
        booking = Booking.objects.create(
            payment=payment,
            user=self.user,
            shop=self.shop,
            slot=slot_booking,
            provider=provider
        )
        
        # Assert: Calculated Fields
        # 1. provider_busy_start = start_time - buffer_before (15m)
        expected_busy_start = start_time - timedelta(minutes=15)
        self.assertEqual(booking.provider_busy_start, expected_busy_start)
        
        # 2. provider_busy_end = start_time + provider_block (20m)
        expected_busy_end = start_time + timedelta(minutes=20)
        self.assertEqual(booking.provider_busy_end, expected_busy_end)
        
        # 3. processing_start = provider_busy_end (since overlap=True)
        self.assertEqual(booking.processing_start, expected_busy_end)
        
        # 4. processing_end = start_time + duration (60m)
        expected_proc_end = start_time + timedelta(minutes=60)
        self.assertEqual(booking.processing_end, expected_proc_end)
        
        # 5. total_end = start_time + duration + buffer_after (5m)
        expected_total_end = start_time + timedelta(minutes=65)
        self.assertEqual(booking.total_end, expected_total_end)

    def test_provider_day_lock_uniqueness(self):
        """Test that ProviderDayLock enforces uniqueness"""
        provider = Provider.objects.create(shop=self.shop, name="LockTest", user=self.owner)
        today = date.today()
        
        ProviderDayLock.objects.create(provider=provider, date=today)
        
        from django.db.utils import IntegrityError
        with self.assertRaises(IntegrityError):
            ProviderDayLock.objects.create(provider=provider, date=today)
