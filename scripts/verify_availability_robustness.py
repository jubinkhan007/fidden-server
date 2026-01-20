
import os
import django
import sys
from datetime import datetime, date

# Setup Django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fidden.settings')
django.setup()

from api.models import AvailabilityRuleSet
from api.utils.availability import _get_ruleset_intervals

def verify_robustness():
    print("Testing parser robustness...")
    
    # Test 1: Full day name + 12h format (User Scenario)
    rules_mixed = {
        "monday": [["09:00 AM", "01:00 PM"], ["02:00 PM", "6:00 PM"]], 
        "fri": [["09:00", "17:00"]] # Normal
    }
    
    ruleset = AvailabilityRuleSet(
        name="Test", timezone="America/New_York", weekly_rules=rules_mixed
    )
    
    # Test Date: Jan 19 2026 (Monday)
    d = date(2026, 1, 19)
    intervals = _get_ruleset_intervals(ruleset, d)
    print(f"Monday Intervals (Expected 2): {len(intervals)}")
    for i in intervals:
        print(f"  {i}")
        
    if len(intervals) == 2:
        print("SUCCESS: Parsed 'monday' + 'AM/PM' correctly.")
    else:
        print("FAILURE: Did not parse 'monday' + 'AM/PM'.")

if __name__ == "__main__":
    verify_robustness()
