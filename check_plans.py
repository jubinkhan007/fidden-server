import os
import django
from decimal import Decimal

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fidden.settings")
django.setup()

from subscriptions.models import SubscriptionPlan

print(f"{'ID':<5} {'Name':<15} {'Price':<10} {'PayPal Plan ID':<20}")
print("-" * 55)

for plan in SubscriptionPlan.objects.all().order_by('id'):
    print(f"{plan.id:<5} {plan.name:<15} {plan.monthly_price:<10} {plan.paypal_plan_id}")
