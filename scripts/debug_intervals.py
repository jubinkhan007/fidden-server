import os
import django
from datetime import date, datetime, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fidden.settings')
django.setup()

from api.models import Shop, Service
from api.utils.availability import get_any_provider_availability
from django.utils import timezone

def debug_slots():
    shop_id = 1
    try:
        shop = Shop.objects.get(id=shop_id)
        print(f"Shop: {shop.name} (ID: {shop.id})")
        print(f"Use Rule Based: {shop.use_rule_based_availability}")
        
        if shop.default_availability_ruleset:
            rs = shop.default_availability_ruleset
            print(f"RuleSet: {rs.name}")
            print(f"Interval Minutes: {rs.interval_minutes}")
            print(f"Timezone: {rs.timezone}")
        else:
            print("No Default RuleSet assigned!")

        # Pick a service
        service = shop.services.first()
        if not service:
            print("No services found.")
            return

        print(f"Service: {service.title} (Duration: {service.duration}m)")
        
        # Test Date: Tomorrow
        target_date = date.today() + timedelta(days=1)
        print(f"Checking slots for: {target_date}")

        # Get Slots
        slots = get_any_provider_availability(
            shop=shop,
            service=service,
            date_obj=target_date
        )
        
        print(f"\nGenerated {len(slots)} slots:")
        for s in slots[:10]:
            print(f" - {s}")

    except Shop.DoesNotExist:
        print(f"Shop {shop_id} not found.")

if __name__ == '__main__':
    debug_slots()
