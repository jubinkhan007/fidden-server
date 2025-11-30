#!/usr/bin/env python
"""
Test Barber Dashboard Endpoints

Verifies that the Barber Dashboard endpoints work correctly.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fidden.settings')
django.setup()

from django.conf import settings
settings.ALLOWED_HOSTS += ['testserver']

from django.test import Client
from django.contrib.auth import get_user_model
from api.models import Shop
from payments.models import Booking
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone

User = get_user_model()

print("=" * 70)
print("BARBER DASHBOARD ENDPOINTS TEST")
print("=" * 70)

# Get a shop owner
shop = Shop.objects.filter(owner__isnull=False).first()
if not shop:
    print("❌ No shop found for testing")
    exit(1)

user = shop.owner
user.set_password('testpass123')
user.save()

# Get auth token
token = str(RefreshToken.for_user(user).access_token)
client = Client()

# Test 1: Today's Appointments
print("\n1️⃣  Testing Today's Appointments")
print("-" * 70)

response = client.get(
    '/api/barber/today-appointments/',
    HTTP_AUTHORIZATION=f'Bearer {token}'
)

if response.status_code == 200:
    data = response.json()
    print(f"✅ Today's Appointments: HTTP {response.status_code}")
    print(f"   Date: {data.get('date')}")
    print(f"   Total Appointments: {data.get('count')}")
    print(f"   Stats: {data.get('stats')}")
else:
    print(f"❌ Failed: HTTP {response.status_code}")
    print(f"   {response.content.decode()}")

# Test 2: Daily Revenue
print("\n2️⃣  Testing Daily Revenue")
print("-" * 70)

response = client.get(
    '/api/barber/daily-revenue/',
    HTTP_AUTHORIZATION=f'Bearer {token}'
)

if response.status_code == 200:
    data = response.json()
    print(f"✅ Daily Revenue: HTTP {response.status_code}")
    print(f"   Date: {data.get('date')}")
    print(f"   Total Revenue: ${data.get('total_revenue')}")
    print(f"   Booking Count: {data.get('booking_count')}")
    print(f"   Avg Value: ${data.get('average_booking_value')}")
else:
    print(f"❌ Failed: HTTP {response.status_code}")
    print(f"   {response.content.decode()}")

# Test 3: No-Show Alerts
print("\n3️⃣  Testing No-Show Alerts")
print("-" * 70)

response = client.get(
    '/api/barber/no-show-alerts/',
    HTTP_AUTHORIZATION=f'Bearer {token}'
)

if response.status_code == 200:
    data = response.json()
    print(f"✅ No-Show Alerts: HTTP {response.status_code}")
    print(f"   Count: {data.get('count')}")
    print(f"   Days: {data.get('days')}")
else:
    print(f"❌ Failed: HTTP {response.status_code}")
    print(f"   {response.content.decode()}")

print("\n" + "=" * 70)
print("✅ BARBER DASHBOARD TESTS COMPLETE")
print("=" * 70)
