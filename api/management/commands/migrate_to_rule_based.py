from django.core.management.base import BaseCommand
from django.db import transaction
from api.models import Shop, Provider, Service, AvailabilityRuleSet, AvailabilityException
from api.utils.availability import to_utc
from datetime import time, datetime, date
import json

class Command(BaseCommand):
    help = 'Migrates existing Shops and Providers to Rule-Based Availability system'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run analysis without making DB changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        self.stdout.write(f"Starting migration... Dry Run: {dry_run}")

        try:
            with transaction.atomic():
                self.migrate_shops(dry_run)
                self.migrate_services(dry_run)
                
                if dry_run:
                    raise Exception("Dry run - rolling back changes")
        except Exception as e:
            if "Dry run" in str(e):
                self.stdout.write(self.style.SUCCESS("Dry run completed successfully (changes rolled back)."))
            else:
                self.stdout.write(self.style.ERROR(f"Error during migration: {e}"))
                raise e

    def migrate_shops(self, dry_run):
        shops = Shop.objects.all()
        for shop in shops:
            self.stdout.write(f"Processing Shop: {shop.name} (ID: {shop.id})...")
            
            # 1. Create RuleSet from Business Hours
            weekly_rules = self._convert_business_hours(shop.business_hours)
            
            if not dry_run:
                rule_set_name = f"Migrated Rules - {shop.name}"
                
                # Check if it already exists to avoid duplicates
                # Since RuleSet doesn't link to Shop, we filter by name which is unique enough for this migration
                rule_set, created = AvailabilityRuleSet.objects.get_or_create(
                    name=rule_set_name,
                    defaults={
                        'timezone': shop.time_zone,
                        'weekly_rules': weekly_rules,
                        'breaks': []
                    }
                )
                
                if created:
                     self.stdout.write(f"   Created RuleSet: {rule_set.name}")
                else:
                    rule_set.weekly_rules = weekly_rules
                    rule_set.timezone = shop.time_zone
                    rule_set.save()
                    self.stdout.write(f"   Updated RuleSet: {rule_set.name}")

                # Update Shop's default ruleset
                shop.default_availability_ruleset = rule_set
                shop.save()
                
                # 2. Assign to Providers who have no ruleset
                providers = Provider.objects.filter(shop=shop, availability_ruleset__isnull=True)
                count = providers.update(availability_ruleset=rule_set)
                if count > 0:
                     self.stdout.write(f"   Assigned RuleSet to {count} providers.")
            else:
                 self.stdout.write(f"   [Dry Run] Would create RuleSet with rules: {json.dumps(weekly_rules)[:100]}...")

    def migrate_services(self, dry_run):
        # Set provider_block_minutes = duration for services where it is NULL
        services = Service.objects.filter(provider_block_minutes__isnull=True)
        count = services.count()
        
        self.stdout.write(f"Found {count} Services with null provider_block_minutes.")
        
        if not dry_run:
            # We have to iterate or use DB expressions.
            # Using update with F() expression is efficient.
            from django.db.models import F
            updated = services.update(provider_block_minutes=F('duration'))
            self.stdout.write(self.style.SUCCESS(f"Updated {updated} services to set provider_block_minutes=duration."))
        else:
            self.stdout.write(f"   [Dry Run] Would update {count} services.")

    def _convert_business_hours(self, business_hours):
        """
        Convert legacy format to AvailabilityRuleSet format.
        Legacy: {"mon": [["09:00", "17:00"]], "tue": ...}
        New: {"mon": [{"start": "09:00", "end": "17:00"}], ...}
        """
        if not business_hours:
            return {}

        new_rules = {}
        # Legacy keys might be "mon" or "monday"? 
        # API/models usually standardized on 3-letter, let's checking typical usage.
        # Assuming keys are already 'mon', 'tue', etc. based on previous view of models.py comments.
        
        valid_days = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
        
        for day, slots in business_hours.items():
            day_key = day.lower()[:3]
            if day_key not in valid_days:
                continue
                
            day_rules = []
            if isinstance(slots, list):
                for slot in slots:
                    # slot is likely ["09:00", "17:00"]
                    if len(slot) == 2:
                        day_rules.append({
                            "start": slot[0],
                            "end": slot[1]
                        })
            
            if day_rules:
                if day_key in new_rules:
                     new_rules[day_key].extend(day_rules)
                else:
                    new_rules[day_key] = day_rules
                    
        return new_rules
