import os
import django

# Point to your Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fidden.settings")  # change backend.settings to your project settings path
django.setup()

# Now you can import your models
from api.models import Shop
from payments.models import ShopStripeAccount
from django.conf import settings
import stripe, time

stripe.api_key = settings.STRIPE_SECRET_KEY

def enable_test_us_account(stripe_account_id, email="owner@example.com"):
    try:
        account = stripe.Account.modify(
            stripe_account_id,
            business_type="individual",
            individual={
                "first_name": "John",
                "last_name": "Doe",
                "dob": {"day": 1, "month": 1, "year": 1990},
                "ssn_last_4": "1234",
                "email": email,
                "phone": "0000000000",
                "address": {
                    "line1": "123 Main Street",
                    "city": "San Francisco",
                    "state": "CA",
                    "postal_code": "94111",
                    "country": "US",
                },
            },
            tos_acceptance={
                "date": int(time.time()),
                "ip": "127.0.0.1",
            },
            capabilities={
                "card_payments": {"requested": True},
                "transfers": {"requested": True},
            },
            business_profile={
                "mcc": "5734",
                "url": "https://970536d26b79.ngrok-free.app",
            },
        )
        print(" Test account enabled:", account.id)
        return account
    except Exception as e:
        print(f"❌ Stripe test onboarding failed: {e}")
        return None


if __name__ == "__main__":
    shop = Shop.objects.get(id=7)
    enable_test_us_account(shop.stripe_account.stripe_account_id, email=shop.owner.email)
