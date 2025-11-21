import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fidden.settings")
django.setup()

from rest_framework.test import APIRequestFactory
from accounts.models import User
from api.models import Shop
from api.serializers import ShopSerializer

def verify_niche():
    print("Verifying Niche Field Implementation...")
    
    # 1. Create dummy user
    email = "niche_test@example.com"
    user, created = User.objects.get_or_create(email=email)
    if created:
        user.set_password("password123")
        user.role = "owner"
        user.save()
        print(f"Created test user: {email}")
    else:
        print(f"Using existing test user: {email}")

    # 2. Create dummy shop with niche
    shop_name = "Test Tattoo Shop"
    niche = "tattoo_artist"
    
    # Clean up existing shop if any
    Shop.objects.filter(owner=user).delete()
    
    shop = Shop.objects.create(
        owner=user,
        name=shop_name,
        niche=niche,
        address="123 Ink St",
        capacity=5,
        start_at="09:00",
        close_at="17:00"
    )
    print(f"Created shop '{shop_name}' with niche '{shop.niche}'")

    # 3. Serialize
    factory = APIRequestFactory()
    request = factory.get('/')
    request.user = user
    
    serializer = ShopSerializer(shop, context={'request': request})
    data = serializer.data
    
    # 4. Verify
    print("\nSerialized Data:")
    print(f"Name: {data.get('name')}")
    print(f"Niche: {data.get('niche')}")
    
    if data.get('niche') == niche:
        print("\n✅ SUCCESS: Niche field is correctly serialized.")
    else:
        print(f"\n❌ FAILURE: Expected niche '{niche}', got '{data.get('niche')}'")

    # Cleanup
    shop.delete()
    user.delete()
    print("Cleanup complete.")

if __name__ == "__main__":
    verify_niche()
