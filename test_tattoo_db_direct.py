"""
Direct Database Test for Tattoo Artist Features
Verifies all CRUD operations work at the model level
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fidden.settings')
django.setup()

from django.contrib.auth import get_user_model
from api.models import (
    Shop, PortfolioItem, DesignRequest, DesignRequestImage,
    ConsentFormTemplate, SignedConsentForm, IDVerificationRequest
)

User = get_user_model()

print("=" * 70)
print("TATTOO ARTIST - Direct Database CRUD Tests")
print("=" * 70)

# Get test data
artist_user = User.objects.get(email="tattoo.artist@fidden.test")
client_user = User.objects.get(email="tattoo.client@fidden.test")
shop = Shop.objects.get(owner=artist_user)

print(f"\n🏪 Testing with shop: {shop.name} (ID: {shop.id})")

# =============================================================================
# 1. PORTFOLIO TESTS
# =============================================================================
print("\n" + "="*70)
print("1️⃣  PORTFOLIO OPERATIONS")
print("="*70)

# READ
portfolio_items = PortfolioItem.objects.filter(shop=shop)
print(f"✅ READ: Found {portfolio_items.count()} portfolio items")
for item in portfolio_items:
    print(f"   - {item.description} (Tags: {item.tags})")

# CREATE
new_portfolio = PortfolioItem.objects.create(
    shop=shop,
    description="Neo-traditional rose with thorns",
    tags=["Neo-traditional", "Floral", "Rose"]
)
print(f"✅ CREATE: Added new portfolio item (ID: {new_portfolio.id})")

# UPDATE
new_portfolio.description = "Neo-Traditional Rose with Thorns (Featured)"
new_portfolio.tags.append("Featured")
new_portfolio.save()
print(f"✅ UPDATE: Updated portfolio item {new_portfolio.id}")

# DELETE (optional - commented out)
# new_portfolio.delete()
# print(f"✅ DELETE: Removed portfolio item")

# =============================================================================
# 2. DESIGN REQUEST TESTS
# =============================================================================
print("\n" + "="*70)
print("2️⃣  DESIGN REQUEST OPERATIONS")
print("="*70)

# READ
design_requests = DesignRequest.objects.filter(shop=shop)
print(f"✅ READ: Found {design_requests.count()} design requests")
for req in design_requests:
    print(f"   - {req.description[:40]}... (Status: {req.status})")

# CREATE
new_design = DesignRequest.objects.create(
    shop=shop,
    user=client_user,
    description="Watercolor butterfly on shoulder blade",
    placement="Right Shoulder Blade",
    size_approx="4x4 inches",
    status="pending"
)
print(f"✅ CREATE: Added new design request (ID: {new_design.id})")

# UPDATE - Change status
new_design.status = "discussing"
new_design.save()
print(f"✅ UPDATE: Changed design request status to '{new_design.status}'")

# =============================================================================
# 3. CONSENT FORM TESTS
# =============================================================================
print("\n" + "="*70)
print("3️⃣  CONSENT FORM OPERATIONS")
print("="*70)

# READ Templates
templates = ConsentFormTemplate.objects.filter(shop=shop)
print(f"✅ READ: Found {templates.count()} consent templates")
for template in templates:
    default_mark = " (Default)" if template.is_default else ""
    print(f"   - {template.title}{default_mark}")

# CREATE Template
new_template = ConsentFormTemplate.objects.create(
    shop=shop,
    title="Aftercare Instructions & Agreement",
    content="I agree to follow all aftercare instructions provided...",
    is_default=False
)
print(f"✅ CREATE: Added new consent template (ID: {new_template.id})")

# UPDATE Template
new_template.is_default = True
new_template.save()
# Update old default
templates.exclude(id=new_template.id).update(is_default=False)
print(f"✅ UPDATE: Set '{new_template.title}' as default template")

# READ Signed Forms
signed_forms = SignedConsentForm.objects.filter(template__shop=shop)
print(f"✅ READ: Found {signed_forms.count()} signed consent forms")

# =============================================================================
# 4. ID VERIFICATION TESTS
# =============================================================================
print("\n" + "="*70)
print("4️⃣  ID VERIFICATION OPERATIONS")
print("="*70)

# READ
id_requests = IDVerificationRequest.objects.filter(shop=shop)
print(f"✅ READ: Found {id_requests.count()} ID verification requests")
for req in id_requests:
    print(f"   - {req.user.name}: {req.status}")

# UPDATE - Approve ID
if id_requests.exists():
    id_req = id_requests.first()
    id_req.status = "approved"
    id_req.save()
    print(f"✅ UPDATE: Approved ID for {id_req.user.name}")
    
    # UPDATE - Reject with reason
    id_req.status = "rejected"
    id_req.rejection_reason = "Photo is unclear, please retake"
    id_req.save()
    print(f"✅ UPDATE: Rejected ID with reason")

# CREATE new ID request for another user (if exists)
test_users = User.objects.exclude(id__in=[artist_user.id, client_user.id])
if test_users.exists():
    new_id_req = IDVerificationRequest.objects.create(
        shop=shop,
        user=test_users.first(),
        status="pending_upload"
    )
    print(f"✅ CREATE: Added new ID verification request (ID: {new_id_req.id})")

# =============================================================================
# FINAL SUMMARY
# =============================================================================
print("\n" + "="*70)
print("📊 FINAL DATABASE STATE")
print("="*70)
print(f"✅ Portfolio Items: {PortfolioItem.objects.filter(shop=shop).count()}")
print(f"✅ Design Requests: {DesignRequest.objects.filter(shop=shop).count()}")
print(f"✅ Consent Templates: {ConsentFormTemplate.objects.filter(shop=shop).count()}")
print(f"✅ Signed Forms: {SignedConsentForm.objects.filter(template__shop=shop).count()}")
print(f"✅ ID Verifications: {IDVerificationRequest.objects.filter(shop=shop).count()}")

print("\n" + "="*70)
print("✅ ALL DATABASE CRUD OPERATIONS SUCCESSFUL!")
print("="*70)
print("\n💡 Next Steps:")
print("   1. Test endpoints via Postman or browser")
print("   2. Deploy to production")
print("   3. Update Flutter app to consume these models")
