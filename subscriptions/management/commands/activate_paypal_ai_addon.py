from django.core.management.base import BaseCommand
from subscriptions.models import ShopSubscription

class Command(BaseCommand):
    help = 'Manually activate PayPal AI Add-on subscription by subscription ID'

    def add_arguments(self, parser):
        parser.add_argument('subscription_id', type=str, help='PayPal subscription ID (e.g., I-H4HEU7ERY40D)')

    def handle(self, *args, **options):
        subscription_id = options['subscription_id']
        
        try:
            sub = ShopSubscription.objects.get(ai_paypal_subscription_id=subscription_id)
            self.stdout.write(f"Found subscription for shop: {sub.shop.name}")
            self.stdout.write(f"Current has_ai_addon status: {sub.has_ai_addon}")
            
            if sub.has_ai_addon:
                self.stdout.write(self.style.WARNING(f"AI Add-on already active for shop: {sub.shop.name}"))
                return
            
            # Activate it
            sub.has_ai_addon = True
            sub.save()
            
            self.stdout.write(self.style.SUCCESS(f"✅ AI Add-on activated for shop: {sub.shop.name}"))
            self.stdout.write(f"New has_ai_addon status: {sub.has_ai_addon}")
        except ShopSubscription.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"❌ No subscription found with ai_paypal_subscription_id: {subscription_id}"))
