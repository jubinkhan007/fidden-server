#!/usr/bin/env python
"""
Diagnostic script to check payment data for calendar badge issues.

Run: docker-compose exec web python manage.py shell < scripts/diagnose_calendar_badges.py
"""
import os
import sys
import django

if 'django' not in sys.modules or not django.apps.apps.ready:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fidden.settings')
    django.setup()

from payments.models import Booking, Payment

print("=" * 70)
print("CALENDAR BADGE DIAGNOSTIC")
print("=" * 70)

# Check bookings 26, 27, 28 specifically
booking_ids = [26, 27, 28]

for bid in booking_ids:
    print(f"\n--- Booking #{bid} ---")
    try:
        booking = Booking.objects.select_related('payment', 'slot__service', 'user').get(id=bid)
        payment = booking.payment

        print(f"  User: {booking.user.email}")
        print(f"  Service: {booking.slot.service.title if booking.slot and booking.slot.service else 'N/A'}")
        print(f"  Booking Status: {booking.status}")
        print(f"\n  PAYMENT DETAILS:")
        print(f"    Payment ID: {payment.id}")
        print(f"    payment.status: '{payment.status}'")
        print(f"    payment.is_deposit: {payment.is_deposit}")
        print(f"    payment.remaining_amount: {payment.remaining_amount} (type: {type(payment.remaining_amount).__name__})")
        print(f"    payment.deposit_status: '{payment.deposit_status}'")
        print(f"    payment.checkout_completed_at: {payment.checkout_completed_at}")
        print(f"    payment.amount: {payment.amount}")
        print(f"    payment.service_price: {payment.service_price}")
        print(f"    payment.deposit_amount: {payment.deposit_amount}")

        # Badge logic analysis
        print(f"\n  BADGE LOGIC ANALYSIS:")

        # Check what badge SHOULD be shown
        if payment.remaining_amount is not None and payment.remaining_amount > 0:
            expected_badge = "BAL_DUE"
            reason = f"remaining_amount ({payment.remaining_amount}) > 0"
        elif payment.remaining_amount == 0 and payment.status == 'succeeded':
            expected_badge = "PAID"
            reason = "remaining_amount == 0 AND status == 'succeeded'"
        elif payment.is_deposit and payment.status != 'succeeded':
            expected_badge = "DEP_DUE"
            reason = f"is_deposit=True AND status='{payment.status}' != 'succeeded'"
        else:
            expected_badge = "NONE"
            reason = f"No badge condition met (remaining={payment.remaining_amount}, status='{payment.status}', is_deposit={payment.is_deposit})"

        print(f"    Expected badge: {expected_badge}")
        print(f"    Reason: {reason}")

        # Check if this is a "fully paid" booking that should show PAID
        if payment.deposit_status == 'credited' and payment.checkout_completed_at:
            print(f"\n  ⚠️  This booking appears FULLY PAID (deposit_status='credited', checkout_completed_at set)")
            if payment.remaining_amount > 0:
                print(f"  ❌ BUT remaining_amount is still {payment.remaining_amount}!")
                print(f"     RUN THE DATA FIX SCRIPT to correct this!")

    except Booking.DoesNotExist:
        print(f"  ❌ Booking #{bid} not found")
    except Exception as e:
        print(f"  ❌ Error: {e}")

print("\n" + "=" * 70)
print("SUMMARY OF ALL PAYMENTS WITH remaining_amount > 0")
print("=" * 70)

problematic = Payment.objects.filter(
    deposit_status='credited',
    checkout_completed_at__isnull=False,
    remaining_amount__gt=0
)
print(f"\nPayments marked as 'credited' with checkout completed but remaining_amount > 0:")
print(f"Count: {problematic.count()}")
for p in problematic:
    print(f"  - Payment #{p.id}: remaining_amount={p.remaining_amount}")

print("\n" + "=" * 70)
print("Done!")
