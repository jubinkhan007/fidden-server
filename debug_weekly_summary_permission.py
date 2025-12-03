import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fidden.settings')
django.setup()

from api.models import Shop
from subscriptions.models import ShopSubscription, SubscriptionPlan

# Find shop 7 (the test user)
shop = Shop.objects.filter(id=7).select_related("subscription__plan").first()

if shop:
    print(f"Shop: {shop.name} (ID: {shop.id})")
    
    # Check what select_related gets
    subscription = getattr(shop, 'subscription', None)
    
    if subscription:
        print(f"\nSubscription found: {subscription}")
        print(f"  - Plan: {subscription.plan}")
        print(f"  - has_ai_addon: {subscription.has_ai_addon}")
        print(f"  - ai_paypal_subscription_id: {subscription.ai_paypal_subscription_id}")
        
        # Check the AI entitlement logic (same as view)
        ai_enabled = False
        if subscription and subscription.plan:
            if subscription.plan.ai_assistant == SubscriptionPlan.AI_INCLUDED or subscription.has_ai_addon:
                ai_enabled = True
        
        print(f"\n✅ AI Enabled Check Result: {ai_enabled}")
        
        if not ai_enabled:
            print("\n❌ PROBLEM: AI should be enabled but check returned False")
            print(f"   Plan AI Assistant: {subscription.plan.ai_assistant if subscription.plan else 'N/A'}")
            print(f"   has_ai_addon value: {subscription.has_ai_addon}")
            print(f"   Expected: has_ai_addon should be True")
    else:
        print("\n❌ No subscription found using select_related")
        
        # Try direct query
        direct_sub = ShopSubscription.objects.filter(shop=shop).first()
        if direct_sub:
            print(f"\n✅ BUT subscription exists via direct query:")
            print(f"   has_ai_addon: {direct_sub.has_ai_addon}")
            print(f"   This means select_related is broken!")
else:
    print("Shop 7 not found")
