from decimal import Decimal
import sys
import os

# Add project root to sys.path
sys.path.insert(0, '/Users/fionabari/fidden-backend')

from payments.utils.deposit import calculate_deposit_details

# Mock Objects
class MockService:
    def __init__(self, is_req=False, dep_type=None, dep_amt=None, dep_pct=None):
        self.is_deposit_required = is_req
        self.deposit_type = dep_type
        self.deposit_amount = dep_amt
        self.deposit_percentage = dep_pct

class MockShop:
    def __init__(self, def_req=True, def_type='percentage', def_amt=None, def_pct=20):
        self.default_is_deposit_required = def_req
        self.default_deposit_type = def_type
        self.default_deposit_amount = def_amt
        self.default_deposit_percentage = def_pct

def test_scenario(name, shop, service, total, expected_is_deposit, expected_amount):
    is_dep, amt = calculate_deposit_details(shop, service, Decimal(total))
    
    status = "✅ PASS" if (is_dep == expected_is_deposit and amt == Decimal(expected_amount)) else "❌ FAIL"
    print(f"[{status}] {name}")
    if status == "❌ FAIL":
        print(f"   Expected: is_deposit={expected_is_deposit}, amount={expected_amount}")
        print(f"   Got:      is_deposit={is_dep}, amount={amt}")

# === Scenarios ===
print("=== Running Deposit Calculation Tests ===\n")

# 1. Standard Shop Default (Percentage)
# Shop: Required=True, Type=Percentage, Pct=20%
# Service: Default (No override)
shop1 = MockShop(def_req=True, def_type='percentage', def_pct=20)
svc1 = MockService(is_req=False)
test_scenario("1. Shop Default Percentage (20% of 100)", shop1, svc1, "100.00", True, "20.00")

# 2. Standard Shop Default (Fixed) - WITH amount field
# Shop: Required=True, Type=Fixed, Amt=15.00
shop2 = MockShop(def_req=True, def_type='fixed', def_amt=15.00)
svc2 = MockService(is_req=False)
test_scenario("2. Shop Default Fixed ($15)", shop2, svc2, "100.00", True, "15.00")

# 3. Shop Default (Fixed) - MISSING amount field (Simulating the bug)
# Shop: Required=True, Type=Fixed, Amt=None
shop3 = MockShop(def_req=True, def_type='fixed', def_amt=None)
svc3 = MockService(is_req=False)
test_scenario("3. Shop Default Fixed (Missing Amount -> Fallback 20%)", shop3, svc3, "100.00", True, "20.00")

# 4. Service Override (Percentage)
# Shop: Default 20%
# Service: Override 50%
shop4 = MockShop(def_req=True, def_type='percentage', def_pct=20)
svc4 = MockService(is_req=True, dep_type='percentage', dep_pct=50)
test_scenario("4. Service Override Percentage (50% of 100)", shop4, svc4, "100.00", True, "50.00")

# 5. Service Override (Fixed)
# Shop: Default 20%
# Service: Override Fixed $10
shop5 = MockShop(def_req=True, def_type='percentage', def_pct=20)
svc5 = MockService(is_req=True, dep_type='fixed', dep_amt=10.00)
test_scenario("5. Service Override Fixed ($10)", shop5, svc5, "100.00", True, "10.00")

# 6. Service Specific NO Deposit
# Shop: Default 20%
# Service: is_deposit_required = False (Explicitly ignored since logic checks service.is_deposit_required first)
# Wait, if service.is_deposit_required is False, logic falls to Shop default.
# If a service wants to FORCE no deposit despite shop setting, we might need logic update.
# Current logic: if service.is_deposit_required is False, it checks Shop.default_is_deposit_required.
# So if Shop says Yes, we charge deposit.
# If the intention of `is_deposit_required=False` on Service is "No deposit for this service", the logic might need tweaking.
# But assuming standard "false means check parent" behavior:
shop6 = MockShop(def_req=True, def_type='percentage', def_pct=20)
svc6 = MockService(is_req=False)
test_scenario("6. Service 'False' falls back to Shop (20%)", shop6, svc6, "100.00", True, "20.00")

# 7. Shop Not Required
shop7 = MockShop(def_req=False)
svc7 = MockService(is_req=False)
test_scenario("7. No Deposit Required (Shop=False)", shop7, svc7, "100.00", False, "100.00")
