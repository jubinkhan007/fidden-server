from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.utils import timezone
from api.models import Shop, Service, ServiceCategory, FitnessPackage, WorkoutTemplate, NutritionPlan, Slot, SlotBooking
from accounts.models import User
from payments.models import Booking, Payment
from datetime import timedelta

class FitnessNicheTests(APITestCase):
    def setUp(self):
        # Create Owner
        self.owner = User.objects.create_user(email='owner@test.com', password='password', role='owner', name='Trainer Bob')
        self.client.force_authenticate(user=self.owner)

        # Create Shop
        self.shop = Shop.objects.create(
            owner=self.owner,
            name="Bob's Gym",
            niches=['fitness_trainer'],
            address="123 Gym St",
            capacity=10,
            start_at="09:00",
            close_at="18:00"
        )
        self.owner.shop = self.shop
        self.owner.save()

        # Create Category & Services
        self.category = ServiceCategory.objects.create(name="Training")
        self.service_1to1 = Service.objects.create(
            shop=self.shop,
            category=self.category,
            title="1:1 Personal Training",
            price=100,
            duration=60,
            capacity=1
        )
        self.service_class = Service.objects.create(
            shop=self.shop,
            category=self.category,
            title="Yoga Class",
            price=20,
            duration=60,
            capacity=10
        )

        # Create Customer
        self.customer = User.objects.create_user(email='customer@test.com', password='password', role='customer', name='Alice')

    def test_dashboard_stats(self):
        # Create some bookings
        start_time = timezone.now() + timedelta(days=1)
        slot = Slot.objects.create(
            shop=self.shop,
            service=self.service_1to1,
            start_time=start_time,
            end_time=start_time + timedelta(hours=1),
            capacity_left=1
        )
        sb = SlotBooking.objects.create(
            shop=self.shop,
            service=self.service_1to1,
            slot=slot,
            start_time=slot.start_time,
            end_time=slot.end_time,
            user=self.customer,
            status='confirmed'
        )
        # Payment signal handles Booking creation when status='succeeded'
        payment = Payment.objects.create(
            booking=sb,
            user=self.customer,
            amount=100,
            total_amount=100,
            payment_method='stripe',
            status='succeeded'
        )

        url = reverse('fitness-dashboard')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['weekly_schedule']['one_to_one'], 1)
        self.assertEqual(response.data['weekly_schedule']['classes'], 0)

    def test_calendar_session_type(self):
        start_time = timezone.now() + timedelta(days=1)
        slot = Slot.objects.create(
            shop=self.shop,
            service=self.service_class,
            start_time=start_time,
            end_time=start_time + timedelta(hours=1),
            capacity_left=10
        )
        sb = SlotBooking.objects.create(
            shop=self.shop,
            service=self.service_class,
            slot=slot,
            start_time=slot.start_time,
            end_time=slot.end_time,
            user=self.customer,
            status='confirmed'
        )
        payment = Payment.objects.create(
            booking=sb,
            user=self.customer,
            amount=20,
            total_amount=20,
            payment_method='stripe',
            status='succeeded'
        )

        url = reverse('calendar')
        response = self.client.get(f"{url}?shop_id={self.shop.id}&start_date={timezone.now().date()}&end_date={(timezone.now() + timedelta(days=7)).date()}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        booking_event = [e for e in response.data if e['event_type'] == 'booking'][0]
        self.assertEqual(booking_event['session_type'], 'class')

    def test_fitness_package_decrement(self):
        # Create a package
        package = FitnessPackage.objects.create(
            shop=self.shop,
            customer=self.customer,
            total_sessions=10,
            sessions_remaining=10,
            price=500
        )

        # Create a booking and mark as completed
        start_time = timezone.now() - timedelta(hours=2)
        slot = Slot.objects.create(
            shop=self.shop,
            service=self.service_1to1,
            start_time=start_time,
            end_time=start_time + timedelta(hours=1),
            capacity_left=1
        )
        sb = SlotBooking.objects.create(
            shop=self.shop,
            service=self.service_1to1,
            slot=slot,
            start_time=slot.start_time,
            end_time=slot.end_time,
            user=self.customer,
            status='confirmed'
        )
        payment = Payment.objects.create(
            booking=sb,
            user=self.customer,
            amount=100,
            total_amount=100,
            payment_method='stripe',
            status='succeeded'
        )
        
        from payments.tasks import complete_past_bookings
        complete_past_bookings()

        package.refresh_from_db()
        self.assertEqual(package.sessions_remaining, 9)

    def test_lean_crud(self):
        # Workout CRUD
        url = reverse('fitness-workout-templates-list')
        response = self.client.post(url, {
            "title": "Leg Day",
            "description": "Intense legs",
            "exercises": [{"name": "Squat", "sets": 3, "reps": 10}],
            "customer": self.customer.id # Added this if it's required by __all__ even if read_only doesn't cover it
        }, format='json')
        if response.status_code != 201:
            print(f"DEBUG WORKOUT 400: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(WorkoutTemplate.objects.count(), 1)

        # Nutrition CRUD
        url = reverse('fitness-nutrition-plans-list')
        response = self.client.post(url, {
            "title": "Keto Diet",
            "notes": "Low carb",
            "external_links": ["https://example.com/keto"]
        }, format='json')
        if response.status_code != 201:
            print(f"DEBUG NUTRITION 400: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(NutritionPlan.objects.count(), 1)
