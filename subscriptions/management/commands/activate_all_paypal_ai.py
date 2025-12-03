from django.core.management.base import BaseCommand
from subscriptions.models import ShopSubscription

class Command(BaseCommand):
    help = 'Activate all pending PayPal AI Add-on subscriptions'

    def handle(self, *args, **options):
        # Find all subscriptions with PayPal AI addon ID but not activated
        pending_subs = ShopSubscription.objects.filter(
            ai_paypal_subscription_id__isnull=False,
            has_ai_addon=False
        )
        
        if not pending_subs.exists():
            self.stdout.write(self.style.SUCCESS("✅ No pending PayPal AI subscriptions found"))
            
            # Show active ones
            active_subs = ShopSubscription.objects.filter(
                ai_paypal_subscription_id__isnull=False,
                has_ai_addon=True
            )
            if active_subs.exists():
                self.stdout.write("\n📋 Active PayPal AI subscriptions:")
                for sub in active_subs:
                    self.stdout.write(f"  - Shop: {sub.shop.name} (ID: {sub.shop.id})")
                    self.stdout.write(f"    PayPal Sub ID: {sub.ai_paypal_subscription_id}")
                    self.stdout.write(f"    has_ai_addon: {sub.has_ai_addon}")
            return
        
        self.stdout.write(f"\n🔍 Found {pending_subs.count()} pending PayPal AI subscription(s):\n")
        
        for sub in pending_subs:
            self.stdout.write(f"  Shop: {sub.shop.name} (ID: {sub.shop.id})")
            self.stdout.write(f"  PayPal Subscription ID: {sub.ai_paypal_subscription_id}")
            self.stdout.write(f"  Current has_ai_addon: {sub.has_ai_addon}")
            
            # Activate it
            sub.has_ai_addon = True
            sub.save()
            
            self.stdout.write(self.style.SUCCESS(f"  ✅ ACTIVATED\n"))
        
        self.stdout.write(self.style.SUCCESS(f"\n✅ Successfully activated {pending_subs.count()} subscription(s)"))
