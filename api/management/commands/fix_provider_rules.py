
from django.core.management.base import BaseCommand
from api.models import AvailabilityRuleSet
from datetime import datetime

class Command(BaseCommand):
    help = 'Fixes corrupted provider availability rules (normalizes day names and time formats)'

    def handle(self, *args, **options):
        self.stdout.write("Scanning availability rulesets...")
        
        mapping = {
            'monday': 'mon', 'tuesday': 'tue', 'wednesday': 'wed',
            'thursday': 'thu', 'friday': 'fri', 'saturday': 'sat', 'sunday': 'sun'
        }
        
        count = 0
        fixed = 0
        
        for ruleset in AvailabilityRuleSet.objects.all():
            count += 1
            raw_rules = ruleset.weekly_rules
            normalized = {}
            changed = False
            
            if not raw_rules:
                continue

            for key, value in raw_rules.items():
                # Fix Key
                norm_key = mapping.get(key.lower(), key.lower())[:3]
                if norm_key != key:
                    changed = True
                
                # Fix Value
                norm_value = []
                for item in value:
                    if isinstance(item, (list, tuple)) and len(item) == 2:
                        s, e = item[0], item[1]
                        s_orig, e_orig = s, e
                        
                        # Fix Start Time
                        try:
                            s_obj = datetime.strptime(s, "%I:%M %p")
                            s = s_obj.strftime("%H:%M")
                            changed = True
                        except ValueError:
                            pass 

                        # Fix End Time
                        try:
                            e_obj = datetime.strptime(e, "%I:%M %p")
                            e = e_obj.strftime("%H:%M")
                            changed = True
                        except ValueError:
                            pass
                            
                        norm_value.append([s, e])
                
                normalized[norm_key] = norm_value
            
            if changed:
                self.stdout.write(f"Fixing ruleset {ruleset.id} ({ruleset.name})...")
                ruleset.weekly_rules = normalized
                ruleset.save()
                fixed += 1
                
        self.stdout.write(self.style.SUCCESS(f"Done. Scanned {count} rulesets, fixed {fixed}."))
