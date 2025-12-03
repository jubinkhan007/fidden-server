"""
Sample Data Generator for Tattoo Artist Features
Creates realistic test data for demo purposes
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fidden.settings')
django.setup()

from django.contrib.auth import get_user_model
from api.models import (
    Shop, PortfolioItem, DesignRequest, DesignRequestImage,
    ConsentFormTemplate, IDVerificationRequest
)
from payments.models import Booking

User = get_user_model()

print("=" * 60)
print("TATTOO ARTIST - Sample Data Generator")
print("=" * 60)

# 1. Get or Create Test Users
print("\n1️⃣  Creating test users...")
artist_user, _ = User.objects.get_or_create(
    email="tattoo.artist@fidden.test",
    defaults={
        "name": "Ink Master Studios",
        "mobile_number": "+15555551234"
    }
)
client_user, _ = User.objects.get_or_create(
    email="tattoo.client@fidden.test",
    defaults={
        "name": "Alex Johnson",
        "mobile_number": "+15555555678"
    }
)
print(f"   ✅ Artist: {artist_user.email}")
print(f"   ✅ Client: {client_user.email}")

# 2. Get or Create Tattoo Shop
print("\n2️⃣  Creating tattoo shop...")
shop, created = Shop.objects.get_or_create(
    owner=artist_user,
    defaults={
        "name": "Ink Master Studios",
        "address": "123 Art Street, Brooklyn, NY",
        "capacity": 5,
        "niche": "tattoo_artist",
        "is_verified": True,
        "status": "verified",
        "start_at": "09:00",  # Required field
        "close_at": "18:00"   # Required field
    }
)
if not created:
    shop.niche = "tattoo_artist"
    shop.save()
print(f"   ✅ Shop: {shop.name} (niche: {shop.niche})")

# 3. Create Portfolio Items
print("\n3️⃣  Creating portfolio items...")
portfolio_items = [
    {"tags": ["Realism", "Portrait"], "description": "Realistic portrait of a loved one"},
    {"tags": ["Traditional", "American"], "description": "Classic sailor jerry style anchor"},
    {"tags": ["Blackwork", "Geometric"], "description": "Sacred geometry mandala"},
]

for idx, item_data in enumerate(portfolio_items, 1):
    portfolio, created = PortfolioItem.objects.get_or_create(
        shop=shop,
        description=item_data["description"],
        defaults={"tags": item_data["tags"]}
    )
    status = "✅ Created" if created else "ℹ️  Exists"
    print(f"   {status}: {item_data['description']}")

# 4. Create Design Requests
print("\n4️⃣  Creating design requests...")
design_requests = [
    {
        "description": "Dragon wrapping around my left forearm",
        "placement": "Left Forearm",
        "size_approx": "8x6 inches",
        "status": "pending"
    },
    {
        "description": "Minimalist mountain range on upper back",
        "placement": "Upper Back",
        "size_approx": "12x4 inches",
        "status": "approved"
    },
]

for req_data in design_requests:
    design_req, created = DesignRequest.objects.get_or_create(
        shop=shop,
        user=client_user,
        description=req_data["description"],
        defaults={
            "placement": req_data["placement"],
            "size_approx": req_data["size_approx"],
            "status": req_data["status"]
        }
    )
    status = "✅ Created" if created else "ℹ️  Exists"
    print(f"   {status}: {req_data['description'][:40]}... ({req_data['status']})")

# 5. Create Consent Form Templates
print("\n5️⃣  Creating consent form templates...")
templates = [
    {
        "title": "General Tattoo Waiver",
        "content": "I acknowledge that tattoos are permanent... [legal text]",
        "is_default": True
    },
    {
        "title": "Minor Consent Form (18+)",
        "content": "I confirm I am over 18 years of age... [legal text]",
        "is_default": False
    },
]

for tmpl_data in templates:
    template, created = ConsentFormTemplate.objects.get_or_create(
        shop=shop,
        title=tmpl_data["title"],
        defaults={
            "content": tmpl_data["content"],
            "is_default": tmpl_data["is_default"]
        }
    )
    status = "✅ Created" if created else "ℹ️  Exists"
    print(f"   {status}: {tmpl_data['title']}")

# 6. Create ID Verification Requests
print("\n6️⃣  Creating ID verification requests...")
id_verification, created = IDVerificationRequest.objects.get_or_create(
    shop=shop,
    user=client_user,
    defaults={
        "status": "pending_upload"
    }
)
status = "✅ Created" if created else "ℹ️  Exists"
print(f"   {status}: ID Verification for {client_user.name}")

print("\n" + "=" * 60)
print("✅ SAMPLE DATA CREATED SUCCESSFULLY!")
print("=" * 60)
print(f"\n📊 Summary:")
print(f"   - Portfolio Items: {PortfolioItem.objects.filter(shop=shop).count()}")
print(f"   - Design Requests: {DesignRequest.objects.filter(shop=shop).count()}")
print(f"   - Consent Templates: {ConsentFormTemplate.objects.filter(shop=shop).count()}")
print(f"   - ID Verifications: {IDVerificationRequest.objects.filter(shop=shop).count()}")
print(f"\n🔑 Test Credentials:")
print(f"   Artist: {artist_user.email}")
print(f"   Client: {client_user.email}")
print(f"   Shop ID: {shop.id}")
