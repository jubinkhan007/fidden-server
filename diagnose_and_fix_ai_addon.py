import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fidden.settings')
django.setup()

from subscriptions.models import ShopSubscription, SubscriptionPlan

print("=" * 60)
print("DIAGNOSTIC: PayPal AI Add-on Status")
print("=" * 60)

# 1. Check Plan ID in database
print("\n1️⃣ AI Add-on Plan Configuration:")
ai_plan = SubscriptionPlan.objects.filter(ai_assistant=SubscriptionPlan.AI_ADDON).first()
if ai_plan:
    print(f"   Plan found: {ai_plan.name}")
    print(f"   PayPal Plan ID: {ai_plan.paypal_plan_id}")
    print(f"   ✅ Correct" if ai_plan.paypal_plan_id == "P-6E691534B0999610JNEQIHII" else "   ❌ WRONG - should be P-6E691534B0999610JNEQIHII")
else:
    print("   ❌ No AI add-on plan found")

# 2. Check all PayPal AI subscriptions
print("\n2️⃣ All PayPal AI Subscriptions:")
all_paypal_ai = ShopSubscription.objects.filter(ai_paypal_subscription_id__isnull=False)

if not all_paypal_ai.exists():
    print("   No PayPal AI subscriptions found")
else:
    for sub in all_paypal_ai:
        status_icon = "✅" if sub.has_ai_addon else "❌"
        print(f"\n   {status_icon} Shop: {sub.shop.name} (ID: {sub.shop.id})")
        print(f"      PayPal Sub ID: {sub.ai_paypal_subscription_id}")
        print(f"      has_ai_addon: {sub.has_ai_addon}")

# 3. Activate all pending
print("\n3️⃣ Activating all pending subscriptions...")
pending = ShopSubscription.objects.filter(
    ai_paypal_subscription_id__isnull=False,
    has_ai_addon=False
)

if pending.exists():
    for sub in pending:
        sub.has_ai_addon = True
        sub.save()
        print(f"   ✅ Activated: {sub.ai_paypal_subscription_id} for {sub.shop.name}")
else:
    print("   No pending subscriptions to activate")

print("\n" + "=" * 60)
print("DONE")
print("=" * 60)
