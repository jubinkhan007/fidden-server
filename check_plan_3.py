import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fidden.settings")
django.setup()

from subscriptions.models import SubscriptionPlan
from django.conf import settings

try:
    plan = SubscriptionPlan.objects.get(id=3)
    print(f"Plan ID: {plan.id}")
    print(f"Plan Name: {plan.name}")
    print(f"PayPal Plan ID: {plan.paypal_plan_id}")
    print(f"Stripe Price ID: {plan.stripe_price_id}")
    
    print(f"Settings PAYPAL_BASE_URL: {getattr(settings, 'PAYPAL_BASE_URL', 'Not Set')}")
    print(f"Settings PAYPAL_CLIENT_ID: {getattr(settings, 'PAYPAL_CLIENT_ID', 'Not Set')[:5]}...")
except SubscriptionPlan.DoesNotExist:
    print("Plan with ID 3 does not exist.")
