"""
Helpers for idempotent transaction logging.

V1 Fix Implementation:
- Ensures checkout transactions are logged from both view and webhook
- Prevents duplicate TransactionLog entries using idempotent checks
- Uses booking_id as stable key for linking
"""
import logging
from decimal import Decimal
from django.utils import timezone

logger = logging.getLogger(__name__)


def ensure_checkout_transaction_logged(payment):
    """
    Idempotently create a TransactionLog for the final checkout payment.
    
    This should be called from:
    - CompleteCheckoutView.post() after successful checkout
    - StripeWebhookView._update_payment_status() when final payment succeeds
    
    Uses booking_id as stable key to ensure we don't create duplicates.
    
    Args:
        payment: Payment model instance with checkout completed
        
    Returns:
        TransactionLog instance or None if not applicable
    """
    from payments.models import TransactionLog, Booking
    
    # Only process if checkout was completed
    if not payment.checkout_completed_at:
        logger.debug(f"Payment {payment.id} has no checkout_completed_at, skipping transaction log")
        return None
    
    # Get the booking
    try:
        if hasattr(payment, 'booking_record'):
            booking = payment.booking_record
        elif hasattr(payment, 'booking'):
            # payment.booking is SlotBooking, get the Booking from it
            booking = Booking.objects.filter(slot=payment.booking).first()
        else:
            logger.warning(f"Cannot find booking for payment {payment.id}")
            return None
    except Exception as e:
        logger.error(f"Error getting booking for payment {payment.id}: {e}")
        return None
    
    if not booking:
        logger.warning(f"No booking found for payment {payment.id}")
        return None
    
    # Calculate the final checkout amount
    remaining = Decimal(str(payment.balance_paid or payment.remaining_amount or 0))
    tip = Decimal(str(payment.tips_amount or 0))
    final_amount = remaining + tip
    
    if final_amount <= 0:
        logger.info(f"No checkout amount for payment {payment.id} (remaining={remaining}, tip={tip})")
        return None
    
    # IDEMPOTENCY: Check if we already have a checkout transaction for this payment
    # Count existing payment-type transactions for this payment
    existing_payment_logs = TransactionLog.objects.filter(
        payment=payment,
        transaction_type="payment",
        status="succeeded"
    )
    
    existing_count = existing_payment_logs.count()
    
    # If there's more than one payment log (deposit + checkout), we already have checkout
    if existing_count > 1:
        logger.info(f"Checkout TransactionLog already exists for payment {payment.id} (count={existing_count})")
        return existing_payment_logs.last()
    
    # Check if we have a log with the exact final amount (to avoid near-duplicates)
    exact_match = existing_payment_logs.filter(amount=final_amount).first()
    if exact_match:
        logger.info(f"Checkout TransactionLog already exists for payment {payment.id}: log_id={exact_match.id}")
        return exact_match
    
    # Check if there's already a deposit log - if so, this will be the checkout log
    deposit_log_exists = existing_count == 1
    
    if not deposit_log_exists:
        # No deposit log exists - this might be a non-deposit payment, skip checkout log
        # OR it's the first payment that should be handled by handle_payment_status signal
        logger.debug(f"No deposit log exists for payment {payment.id}, may be handled by signal")
        return None
    
    # Create the checkout transaction log
    try:
        transaction = TransactionLog.objects.create(
            transaction_type="payment",
            payment=payment,
            user=payment.user,
            shop=booking.shop,
            slot=booking.slot if hasattr(booking, 'slot') else None,
            service=booking.slot.service if hasattr(booking, 'slot') and booking.slot else None,
            amount=final_amount,
            currency=payment.currency or "usd",
            status="succeeded",
        )
        logger.info(
            f"[Checkout] Created TransactionLog id={transaction.id} for payment {payment.id}, "
            f"booking {booking.id}, amount=${float(final_amount):.2f} (remaining=${float(remaining):.2f}, tip=${float(tip):.2f})"
        )
        return transaction
    except Exception as e:
        logger.error(f"Failed to create checkout TransactionLog for payment {payment.id}: {e}", exc_info=True)
        return None


def get_payment_totals(payment):
    """
    Calculate total amounts for a payment including deposit, remaining, and tip.
    
    Args:
        payment: Payment model instance
        
    Returns:
        dict with deposit_collected, remaining_collected, tip_collected, total_collected
    """
    deposit_collected = float(payment.deposit_paid or payment.amount or 0)
    remaining_collected = float(payment.balance_paid or 0)
    tip_collected = float(payment.tips_amount or 0)
    total_collected = deposit_collected + remaining_collected + tip_collected
    
    return {
        "deposit_collected": deposit_collected,
        "remaining_collected": remaining_collected,
        "tip_collected": tip_collected,
        "total_collected": total_collected,
    }
