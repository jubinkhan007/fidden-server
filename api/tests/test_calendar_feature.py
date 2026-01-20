from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta, date
from decimal import Decimal

from api.models import Shop, Provider, Service, ServiceCategory, BlockedTime, SlotBooking, Slot
from payments.models import Booking, Payment
from django.contrib.auth import get_user_model

User = get_user_model()

class CalendarFeatureTest(APITestCase):
    def setUp(self):
        # 1. Setup Data
        self.owner = User.objects.create_user(email='owner@test.com', password='password', role='owner')
        self.customer = User.objects.create_user(email='client@test.com', password='password', role='user')
        
        # Create Shop
        self.shop = Shop.objects.create(
            owner=self.owner, 
            name="Test Shop", 
            default_is_deposit_required=True,
            default_deposit_percentage=50,
            capacity=5,
            start_at="09:00",
            close_at="17:00"
        )
        self.owner.shop = self.shop
        self.owner.save()
        
        # Create Provider & Service
        self.provider = Provider.objects.create(name="Jane Doe", shop=self.shop)
        self.category = ServiceCategory.objects.create(name="Hair")
        self.service = Service.objects.create(
            shop=self.shop, title="Cut", price=100, duration=60, 
            category=self.category,
            is_deposit_required=True, deposit_percentage=50
        )
        
        # Authenticate as owner
        self.client.force_authenticate(user=self.owner)
        self.url = reverse('calendar')

    def test_calendar_response_structure_and_status(self):
        """
        Verify:
        - Confirmed booking
        - Blocked time
        - Response structure (unified list)
        """
        now = timezone.now()
        start = now + timedelta(days=1)
        end = start + timedelta(hours=1)
        
        # Create Booking (Confirmed)
        slot = Slot.objects.create(shop=self.shop, service=self.service, start_time=start, end_time=end)
        s_booking = SlotBooking.objects.create(
            user=self.customer, shop=self.shop, service=self.service, slot=slot, 
            start_time=start, end_time=end, status='confirmed', provider=self.provider
        )
        # Create Payment (Succeeded)
        payment = Payment.objects.create(
            user=self.customer, amount=100, status='succeeded', 
            is_deposit=True, deposit_status='credited',
            booking=s_booking
        )
        booking = Booking.objects.create(
            user=self.customer, shop=self.shop, slot=s_booking, 
            payment=payment, status='active', provider=self.provider,
            provider_busy_start=start, provider_busy_end=end
        )
        
        # Create BlockedTime
        block_start = start + timedelta(hours=2)
        block_end = block_start + timedelta(hours=1)
        BlockedTime.objects.create(
            shop=self.shop, provider=self.provider, 
            start_at=block_start, end_at=block_end, reason='break'
        )
        
        # Execute GET
        params = {
            'shop_id': self.shop.id,
            'start_date': now.date(),
            'end_date': (now + timedelta(days=7)).date()
        }
        response = self.client.get(self.url, params)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        
        self.assertEqual(len(data), 2)
        
        # Verify Booking Event
        b_evt = next(d for d in data if d['event_type'] == 'booking')
        self.assertEqual(b_evt['calendar_status'], 'CONFIRMED')
        self.assertIn('PAID', b_evt['badges'])
        self.assertEqual(b_evt['timezone_id'], str(timezone.get_current_timezone_name())) # or None
        
        # Verify Blocked Event
        blk_evt = next(d for d in data if d['event_type'] == 'blocked')
        self.assertEqual(blk_evt['calendar_status'], 'BLOCKED')
        self.assertEqual(blk_evt['blocked_reason'], 'break')

    def test_badges_dep_due_and_forms(self):
        """
        Verify DEP_DUE badge and FORMS badge
        """
        now = timezone.now()
        start = now + timedelta(days=2)
        end = start + timedelta(hours=1)
        
        slot = Slot.objects.create(shop=self.shop, service=self.service, start_time=start, end_time=end)
        s_booking = SlotBooking.objects.create(
            user=self.customer, shop=self.shop, service=self.service, slot=slot, 
            start_time=start, end_time=end, status='confirmed', provider=self.provider
        )
        
        # Payment requiring deposit but NOT paid
        payment = Payment.objects.create(
            user=self.customer, amount=100, status='pending', 
            is_deposit=True, deposit_status='held', # Not credited yet
            deposit_amount=50,
            booking=s_booking
        )
        
        booking = Booking.objects.create(
            user=self.customer, shop=self.shop, slot=s_booking, 
            payment=payment, status='active', 
            provider_busy_start=start, provider_busy_end=end,
             # Needs forms
            forms_required=True, forms_completed=False
        )
        
        params = {
            'shop_id': self.shop.id,
            'start_date': now.date(),
            'end_date': (now + timedelta(days=7)).date()
        }
        res = self.client.get(self.url, params)
        item = res.data[0]
        
        self.assertIn('DEP_DUE', item['badges']) # Deposit due because status != credited
        self.assertIn('FORMS', item['badges'])   # Forms required & incomplete
        self.assertEqual(item['calendar_status'], 'PENDING') # Should be pending because deposit due
        
    def test_new_customer_badge(self):
        """
        Verify NEW badge appears only on first active booking
        """
        now = timezone.now()
        
        # 1. First booking (Should be NEW)
        start1 = now + timedelta(days=3)
        slot1 = Slot.objects.create(shop=self.shop, service=self.service, start_time=start1, end_time=start1+timedelta(hours=1))
        s_booking1 = SlotBooking.objects.create(user=self.customer, shop=self.shop, service=self.service, slot=slot1, start_time=start1, end_time=start1+timedelta(hours=1), status='confirmed')
        payment1 = Payment.objects.create(user=self.customer, amount=100, status='succeeded', booking=s_booking1)
        
        booking1 = Booking.objects.create(
            user=self.customer, shop=self.shop, slot=s_booking1, payment=payment1, 
            status='active', provider_busy_start=start1
        )
        
        # Query just this one
        res = self.client.get(self.url, {'shop_id': self.shop.id, 'start_date': start1.date(), 'end_date': start1.date()})
        self.assertIn('NEW', res.data[0]['badges'])
        
        # 2. Second booking (Should NOT be NEW)
        start2 = now + timedelta(days=4)
        slot2 = Slot.objects.create(shop=self.shop, service=self.service, start_time=start2, end_time=start2+timedelta(hours=1))
        s_booking2 = SlotBooking.objects.create(user=self.customer, shop=self.shop, service=self.service, slot=slot2, start_time=start2, end_time=start2+timedelta(hours=1), status='confirmed')
        payment2 = Payment.objects.create(user=self.customer, amount=100, status='succeeded', booking=s_booking2)
        
        booking2 = Booking.objects.create(
            user=self.customer, shop=self.shop, slot=s_booking2, payment=payment2, 
            status='active', provider_busy_start=start2
        )
        
        # Query second booking
        res2 = self.client.get(self.url, {'shop_id': self.shop.id, 'start_date': start2.date(), 'end_date': start2.date()})
        # Note: The logic in serializer might fetch existing 'completed/active' bookings. 
        # Since booking1 is 'active', it counts as history for booking2.
        self.assertNotIn('NEW', res2.data[0]['badges'])
