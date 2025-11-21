import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fidden.settings")
django.setup()

from rest_framework.test import APIRequestFactory
from accounts.models import User
from accounts.views import LoginView
from api.models import Shop

def verify_login_niche():
    print("Verifying Niche in Login Response...")
    
    # 1. Create dummy user
    email = "login_niche_test@example.com"
    password = "password123"
    user, created = User.objects.get_or_create(email=email)
    user.set_password(password)
    user.role = "owner"
    user.is_verified = True
    user.is_active = True
    user.save()

    # 2. Create dummy shop with niche
    shop_name = "Login Test Shop"
    niche = "fitness_trainer"
    
    # Clean up existing shop if any
    Shop.objects.filter(owner=user).delete()
    
    shop = Shop.objects.create(
        owner=user,
        name=shop_name,
        niche=niche,
        address="123 Gym St",
        capacity=10,
        start_at="06:00",
        close_at="22:00"
    )
    print(f"Created user '{email}' and shop '{shop_name}' with niche '{niche}'")

    # 3. Simulate Login
    factory = APIRequestFactory()
    request = factory.post(
        '/accounts/login/', 
        {"email": email, "password": password}, 
        format='json'
    )
    view = LoginView.as_view()
    response = view(request)
    
    # 4. Verify Response
    data = response.data
    print("\nLogin Response Data:")
    print(f"Email: {data.get('email')}")
    print(f"Shop ID: {data.get('shop_id')}")
    print(f"Shop Niche: {data.get('shop_niche')}")
    
    if data.get('shop_niche') == niche and data.get('shop_id') == shop.id:
        print("\n✅ SUCCESS: Login response contains correct shop niche and ID.")
    else:
        print(f"\n❌ FAILURE: Expected niche '{niche}', got '{data.get('shop_niche')}'")

    # Cleanup
    shop.delete()
    user.delete()
    print("Cleanup complete.")

if __name__ == "__main__":
    verify_login_niche()
