#!/usr/bin/env python
"""
One-time script to fix remaining_amount for bookings that were fully paid
but still have remaining_amount > 0 due to webhook bug.

A booking is considered fully paid if:
- payment.deposit_status == 'credited' AND
- payment.checkout_completed_at is NOT NULL

Run: python manage.py shell < scripts/fix_paid_bookings_remaining_amount.py
Or:  docker-compose exec web python manage.py shell < scripts/fix_paid_bookings_remaining_amount.py
"""
import os
import sys
import django

# Setup Django if running standalone
if 'django' not in sys.modules or not django.apps.apps.ready:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fidden.settings')
    django.setup()

from decimal import Decimal
from payments.models import Payment

# Find payments that are fully paid but still have remaining_amount > 0
fully_paid_with_balance = Payment.objects.filter(
    deposit_status='credited',
    checkout_completed_at__isnull=False,
    remaining_amount__gt=0
)

count = fully_paid_with_balance.count()
print(f"Found {count} fully paid bookings with incorrect remaining_amount > 0")

if count > 0:
    print("\nDetails:")
    for p in fully_paid_with_balance:
        print(f"  Payment #{p.id}: remaining_amount={p.remaining_amount}, "
              f"deposit_status={p.deposit_status}, "
              f"checkout_completed_at={p.checkout_completed_at}")

    # Fix them
    updated = fully_paid_with_balance.update(remaining_amount=Decimal('0.00'))
    print(f"\n✅ Fixed {updated} payment records - set remaining_amount = 0")
else:
    print("No records to fix.")

# Also check for non-deposit full payments that may have wrong remaining_amount
non_deposit_wrong = Payment.objects.filter(
    is_deposit=False,
    status='succeeded',
    remaining_amount__gt=0
)

count2 = non_deposit_wrong.count()
if count2 > 0:
    print(f"\nFound {count2} non-deposit full payments with remaining_amount > 0")
    for p in non_deposit_wrong:
        print(f"  Payment #{p.id}: remaining_amount={p.remaining_amount}, "
              f"is_deposit={p.is_deposit}, status={p.status}")

    updated2 = non_deposit_wrong.update(remaining_amount=Decimal('0.00'))
    print(f"✅ Fixed {updated2} non-deposit payment records")

print("\nDone!")
