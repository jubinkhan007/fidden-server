from django.core.management.base import BaseCommand
from django.conf import settings
from subscriptions.models import SubscriptionPlan

class Command(BaseCommand):
    help = 'Syncs PayPal Plan IDs from settings to the database'

    def handle(self, *args, **options):
        # 1. Momentum
        momentum_id = getattr(settings, 'PAYPAL_PLAN_MOMENTUM_ID', None)
        if momentum_id:
            count = SubscriptionPlan.objects.filter(name=SubscriptionPlan.MOMENTUM).update(paypal_plan_id=momentum_id)
            if count:
                self.stdout.write(self.style.SUCCESS(f'Updated Momentum plan with ID: {momentum_id}'))
            else:
                self.stdout.write(self.style.WARNING('Momentum plan not found in DB'))
        else:
            self.stdout.write(self.style.WARNING('PAYPAL_PLAN_MOMENTUM_ID not set in settings'))

        # 2. Icon
        icon_id = getattr(settings, 'PAYPAL_PLAN_ICON_ID', None)
        if icon_id:
            count = SubscriptionPlan.objects.filter(name=SubscriptionPlan.ICON).update(paypal_plan_id=icon_id)
            if count:
                self.stdout.write(self.style.SUCCESS(f'Updated Icon plan with ID: {icon_id}'))
            else:
                self.stdout.write(self.style.WARNING('Icon plan not found in DB'))
        else:
            self.stdout.write(self.style.WARNING('PAYPAL_PLAN_ICON_ID not set in settings'))

        # 3. AI Add-on
        ai_id = getattr(settings, 'PAYPAL_PLAN_AI_ADDON_ID', None)
        if ai_id:
            # Assuming AI add-on is identified by name="AI Assistant" or ai_assistant="addon"
            # Based on tests, name="AI Assistant" and ai_assistant=AI_ADDON
            count = SubscriptionPlan.objects.filter(ai_assistant=SubscriptionPlan.AI_ADDON).update(paypal_plan_id=ai_id)
            if count:
                self.stdout.write(self.style.SUCCESS(f'Updated AI Add-on plan with ID: {ai_id}'))
            else:
                self.stdout.write(self.style.WARNING('AI Add-on plan not found in DB'))
        else:
            self.stdout.write(self.style.WARNING('PAYPAL_PLAN_AI_ADDON_ID not set in settings'))
