
import os
import django
import sys
from datetime import datetime, date

# Setup Django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fidden.settings')
django.setup()

from api.models import Shop, Service, Provider, AvailabilityRuleSet, ServiceCategory
from api.utils.availability import provider_available_starts, _get_ruleset_intervals

def debug_availability_simulation():
    try:
        # Shop
        try:
            shop = Shop.objects.get(id=7)
        except Shop.DoesNotExist:
            print("Shop 7 not found, using first shop")
            shop = Shop.objects.first()
        
        shop.use_rule_based_availability = True
        shop.save()
        print(f"Shop: {shop.name} ({shop.id})")

        # Category for service
        cat, _ = ServiceCategory.objects.get_or_create(name="Debug Category")

        # Service
        service, _ = Service.objects.get_or_create(
            shop=shop,
            title="Debug Service 56",
            defaults={'price': 100, 'duration': 30, 'category': cat}
        )
        print(f"Service: {service.title} (Duration: {service.duration})")

        # Rules: Normalized
        normalized_rules = {
            "mon": [["09:00", "13:00"], ["14:00", "19:00"]],
            "fri": [["09:00", "17:00"]]
        }
        
        # Provider
        provider, _ = Provider.objects.get_or_create(
            shop=shop,
            name="Debug Provider Normal",
            defaults={'provider_type': 'employee'}
        )
        
        # Ensure ruleset
        if not provider.availability_ruleset:
            ruleset = AvailabilityRuleSet.objects.create(
                name="Debug Rules Normal",
                timezone="America/New_York",
                weekly_rules=normalized_rules
            )
            provider.availability_ruleset = ruleset
            provider.save()
        else:
            provider.availability_ruleset.weekly_rules = normalized_rules
            provider.availability_ruleset.timezone = "America/New_York"
            provider.availability_ruleset.save()
            
        print(f"Provider: {provider.name}")
        print(f"Rules: {provider.availability_ruleset.weekly_rules}")

        dates = [date(2026, 1, 16), date(2026, 1, 19)]
        from api.utils.availability import resolve_timezone_id
        print(f"Resolved TZ: {resolve_timezone_id(provider)}")

        for d in dates: 
            day_key = d.strftime("%a").lower()
            print(f"\n--- Checking {d} ({day_key}) ---")
            
            # Check raw intervals
            intervals = _get_ruleset_intervals(provider.availability_ruleset, d)
            print(f"Raw Intervals: {intervals}")
            
            slots = provider_available_starts(provider, service, d)
            print(f"Slots ({len(slots)}):")
            for s in slots:
                print(f"  {s}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_availability_simulation()
