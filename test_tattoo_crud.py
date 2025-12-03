"""
Comprehensive CRUD Test Script for Tattoo Artist Features
Tests all endpoints with actual API calls
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fidden.settings')
django.setup()

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from api.models import (
    Shop, PortfolioItem, DesignRequest,
    ConsentFormTemplate, SignedConsentForm, IDVerificationRequest
)

User = get_user_model()

# Initialize API client
client = APIClient()

# Test users and shop
artist_user = User.objects.get(email="tattoo.artist@fidden.test")
client_user = User.objects.get(email="tattoo.client@fidden.test")
shop = Shop.objects.get(owner=artist_user)

# Generate JWT token for authentication
refresh = RefreshToken.for_user(artist_user)
access_token = str(refresh.access_token)

print("=" * 70)
print("TATTOO ARTIST API - CRUD TEST SUITE")
print("=" * 70)
print(f"\n🔐 Authenticating as: {artist_user.email}")
print(f"🏪 Testing shop: {shop.name} (ID: {shop.id})")

client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')

# Helper function to print results
def print_result(test_name, response):
    status = response.status_code
    emoji = "✅" if 200 <= status < 300 else "❌"
    print(f"\n{emoji} {test_name}")
    print(f"   Status: {status}")
    if 200 <= status < 300:
        data = response.json() if hasattr(response, 'json') else response.data
        if isinstance(data, list):
            print(f"   Results: {len(data)} items")
        elif isinstance(data, dict):
            print(f"   Data keys: {list(data.keys())[:5]}")
    else:
        print(f"   Error: {response.data if hasattr(response, 'data') else 'Unknown'}")
    return response

# =============================================================================
# 1. PORTFOLIO TESTS
# =============================================================================
print("\n" + "="*70)
print("1️⃣  PORTFOLIO CRUD TESTS")
print("="*70)

# List Portfolio
response = client.get('/api/portfolio/')
print_result("GET /api/portfolio/ - List all portfolio items", response)

# Create Portfolio Item
new_portfolio = {
    "shop": shop.id,
    "description": "Japanese style koi fish",
    "tags": ["Japanese", "Colorful", "Koi"]
}
response = client.post('/api/portfolio/', new_portfolio, format='json')
result = print_result("POST /api/portfolio/ - Create new portfolio item", response)
if 200 <= result.status_code < 300:
    portfolio_id = result.data.get('id')
    
    # Update Portfolio Item
    update_data = {"description": "Japanese Style Koi Fish (Updated)", "tags": ["Japanese", "Colorful"]}
    response = client.patch(f'/api/portfolio/{portfolio_id}/', update_data, format='json')
    print_result(f"PATCH /api/portfolio/{portfolio_id}/ - Update portfolio item", response)
    
    # Delete Portfolio Item (optional - uncomment to test)
    # response = client.delete(f'/api/portfolio/{portfolio_id}/')
    # print_result(f"DELETE /api/portfolio/{portfolio_id}/ - Delete portfolio item", response)

# =============================================================================
# 2. DESIGN REQUEST TESTS
# =============================================================================
print("\n" + "="*70)
print("2️⃣  DESIGN REQUEST CRUD TESTS")
print("="*70)

# List Design Requests
response = client.get('/api/design-requests/')
print_result("GET /api/design-requests/ - List all design requests", response)

# Create Design Request
new_design_request = {
    "shop": shop.id,
    "user": client_user.id,
    "description": "Phoenix rising from ashes on my chest",
    "placement": "Chest",
    "size_approx": "10x10 inches",
    "status": "pending"
}
response = client.post('/api/design-requests/', new_design_request, format='json')
result = print_result("POST /api/design-requests/ - Create new design request", response)
if 200 <= result.status_code < 300:
    design_id = result.data.get('id')
    
    # Update Design Request Status
    update_data = {"status": "approved"}
    response = client.patch(f'/api/design-requests/{design_id}/', update_data, format='json')
    print_result(f"PATCH /api/design-requests/{design_id}/ - Approve design request", response)

# =============================================================================
# 3. CONSENT FORM TESTS
# =============================================================================
print("\n" + "="*70)
print("3️⃣  CONSENT FORM CRUD TESTS")
print("="*70)

# List Consent Templates
response = client.get('/api/consent-forms/templates/')
print_result("GET /api/consent-forms/templates/ - List all consent templates", response)

# Create Consent Template
new_template = {
    "shop": shop.id,
    "title": "Health Screening Form",
    "content": "Do you have any medical conditions we should be aware of? ...",
    "is_default": False
}
response = client.post('/api/consent-forms/templates/', new_template, format='json')
result = print_result("POST /api/consent-forms/templates/ - Create new consent template", response)
if 200 <= result.status_code < 300:
    template_id = result.data.get('id')
    
    # Update Template
    update_data = {"title": "Health & Medical Screening Form"}
    response = client.patch(f'/api/consent-forms/templates/{template_id}/', update_data, format='json')
    print_result(f"PATCH /api/consent-forms/templates/{template_id}/ - Update template", response)

# List Signed Consent Forms
response = client.get('/api/consent-forms/signed/')
print_result("GET /api/consent-forms/signed/ - List all signed forms", response)

# =============================================================================
# 4. ID VERIFICATION TESTS
# =============================================================================
print("\n" + "="*70)
print("4️⃣  ID VERIFICATION CRUD TESTS")
print("="*70)

# List ID Verifications
response = client.get('/api/id-verification/')
print_result("GET /api/id-verification/ - List all ID verification requests", response)

# Get specific ID verification
existing_id_verification = IDVerificationRequest.objects.filter(shop=shop).first()
if existing_id_verification:
    # Update ID Verification Status
    update_data = {"status": "approved"}
    response = client.patch(f'/api/id-verification/{existing_id_verification.id}/', update_data, format='json')
    print_result(f"PATCH /api/id-verification/{existing_id_verification.id}/ - Approve ID", response)
    
    # Reject with reason
    update_data = {"status": "rejected", "rejection_reason": "Image too blurry"}
    response = client.patch(f'/api/id-verification/{existing_id_verification.id}/', update_data, format='json')
    print_result(f"PATCH /api/id-verification/{existing_id_verification.id}/ - Reject ID", response)

# =============================================================================
# SUMMARY
# =============================================================================
print("\n" + "="*70)
print("📊 TEST SUMMARY")
print("="*70)
print(f"✅ Portfolio Items: {PortfolioItem.objects.filter(shop=shop).count()}")
print(f"✅ Design Requests: {DesignRequest.objects.filter(shop=shop).count()}")
print(f"✅ Consent Templates: {ConsentFormTemplate.objects.filter(shop=shop).count()}")
print(f"✅ Signed Forms: {SignedConsentForm.objects.filter(template__shop=shop).count()}")
print(f"✅ ID Verifications: {IDVerificationRequest.objects.filter(shop=shop).count()}")
print("\n" + "="*70)
print("✅ ALL CRUD TESTS COMPLETED!")
print("="*70)
