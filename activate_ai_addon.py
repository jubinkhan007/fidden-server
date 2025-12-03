import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fidden.settings')
django.setup()

from subscriptions.models import ShopSubscription

# Find the subscription with this PayPal ID
subscription_id = "I-H4HEU7ERY40D"

try:
    sub = ShopSubscription.objects.get(ai_paypal_subscription_id=subscription_id)
    print(f"Found subscription for shop: {sub.shop.name}")
    print(f"Current has_ai_addon status: {sub.has_ai_addon}")
    
    # Activate it
    sub.has_ai_addon = True
    sub.save()
    
    print(f"✅ AI Add-on activated for shop: {sub.shop.name}")
    print(f"New has_ai_addon status: {sub.has_ai_addon}")
except ShopSubscription.DoesNotExist:
    print(f"❌ No subscription found with ai_paypal_subscription_id: {subscription_id}")
