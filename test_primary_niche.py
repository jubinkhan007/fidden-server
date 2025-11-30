#!/usr/bin/env python
"""
Test Primary Niche + Capabilities Implementation

Verifies that the API returns the correct structure for the new dashboard spec.
"""
import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fidden.settings')
django.setup()

from django.conf import settings
settings.ALLOWED_HOSTS += ['testserver']

from django.test import Client
from django.contrib.auth import get_user_model
from api.models import Shop
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()

print("=" * 70)
print("PRIMARY NICHE + CAPABILITIES TEST")
print("=" * 70)

# Test 1: Shop Serializer
print("\n1️⃣  Testing Shop Serializer")
print("-" * 70)

from api.serializers import ShopSerializer

# Find or create a multi-niche shop
shop = Shop.objects.exclude(niches=[]).first()
if not shop:
    # Create one if not exists
    user = User.objects.filter(shop__isnull=False).first()
    if user:
        shop = user.shop
        shop.niches = ['barber', 'massage_therapist', 'esthetician']
        shop.save()
        shop.refresh_from_db()

if shop:
    serializer = ShopSerializer(shop)
    data = serializer.data
    
    print(f"Shop: {shop.name}")
    print(f"Niches: {shop.niches}")
    print(f"\nAPI Response:")
    print(f"  - primary_niche: {data.get('primary_niche')}")
    print(f"  - capabilities: {data.get('capabilities')}")
    
    # Verification
    expected_primary = shop.niches[0]
    expected_capabilities = shop.niches[1:]
    
    if data.get('primary_niche') == expected_primary:
        print(f"✅ primary_niche matches first item: {expected_primary}")
    else:
        print(f"❌ primary_niche mismatch! Expected {expected_primary}, got {data.get('primary_niche')}")
        
    if data.get('capabilities') == expected_capabilities:
        print(f"✅ capabilities matches rest of list: {expected_capabilities}")
    else:
        print(f"❌ capabilities mismatch! Expected {expected_capabilities}, got {data.get('capabilities')}")
else:
    print("❌ No shop found for testing")

# Test 2: Login Endpoint
print("\n2️⃣  Testing Login Endpoint")
print("-" * 70)

client = Client()
user = shop.owner if shop else None

if user:
    # Ensure user has password
    user.set_password('testpass123')
    user.save()
    
    response = client.post('/accounts/login/', {
        'email': user.email,
        'password': 'testpass123'
    }, content_type='application/json')
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Login successful")
        print(f"Response fields:")
        print(f"  - primary_niche: {data.get('primary_niche')}")
        print(f"  - capabilities: {data.get('capabilities')}")
        
        if 'primary_niche' in data and 'capabilities' in data:
            print(f"✅ Login response contains new fields")
        else:
            print(f"❌ Login response missing new fields")
    else:
        print(f"❌ Login failed: {response.status_code}")

print("\n" + "=" * 70)
print("VERIFICATION COMPLETE")
print("=" * 70)
