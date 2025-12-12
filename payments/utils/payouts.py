"""
Payout utilities for PayPal booking payments.
Transfers shop's share (after commission) to their Stripe Connect account.
"""
import logging
from decimal import Decimal
from django.utils import timezone
import stripe
from django.conf import settings

from payments.models import Payment, ShopPayout

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY


def process_shop_payout(payment: Payment) -> ShopPayout:
    """
    Calculate commission (from total service price) and transfer to shop's Stripe Connect.
    
    Commission Logic:
    - Foundation: 10% of service price (often equals deposit, so net = 0)
    - Momentum/Icon: 0%, so net = deposit amount
    
    Args:
        payment: The Payment object for the PayPal booking
        
    Returns:
        ShopPayout: The created payout record
    """
    shop = payment.booking.shop
    service = payment.booking.service
    subscription = getattr(shop, "subscription", None)
    plan = getattr(subscription, "plan", None)
    
    # Commission is based on TOTAL SERVICE PRICE, not deposit
    service_price = float(
        service.discount_price if service.discount_price and service.discount_price > 0 
        else service.price
    )
    commission_rate = float(plan.commission_rate) if plan and plan.commission_rate else 0.0
    commission = (service_price * commission_rate) / 100.0
    
    # Net = deposit - commission (can be 0 for Foundation)
    deposit = float(payment.amount)
    net = max(deposit - commission, 0)  # Never negative
    
    # Create payout record
    payout = ShopPayout.objects.create(
        shop=shop,
        payment=payment,
        gross_amount=Decimal(str(deposit)),
        commission_amount=Decimal(str(min(commission, deposit))),  # Cap at deposit
        net_amount=Decimal(str(net)),
        commission_rate=Decimal(str(commission_rate)),
        status=ShopPayout.STATUS_PENDING,
    )
    
    # If no money to transfer (Foundation case), mark as completed immediately
    if net <= 0:
        payout.status = ShopPayout.STATUS_COMPLETED
        payout.completed_at = timezone.now()
        payout.save()
        logger.info(
            f"PayPal Payout: No transfer needed for payment {payment.id} "
            f"(commission ${commission:.2f} >= deposit ${deposit:.2f})"
        )
        return payout
    
    # Transfer via Stripe
    try:
        shop_stripe = getattr(shop, "stripe_account", None)
        if not shop_stripe or not shop_stripe.stripe_account_id:
            raise ValueError(f"Shop {shop.name} has no Stripe Connect account")
        
        payout.status = ShopPayout.STATUS_PROCESSING
        payout.save()
        
        transfer = stripe.Transfer.create(
            amount=int(net * 100),  # Convert to cents
            currency="usd",
            destination=shop_stripe.stripe_account_id,
            metadata={
                "payment_id": str(payment.id),
                "payout_id": str(payout.id),
                "shop_id": str(shop.id),
                "source": "paypal_booking",
            },
        )
        
        payout.stripe_transfer_id = transfer.id
        payout.status = ShopPayout.STATUS_COMPLETED
        payout.completed_at = timezone.now()
        payout.save()
        
        logger.info(
            f"PayPal Payout: Transferred ${net:.2f} to {shop.name} "
            f"(Stripe transfer: {transfer.id})"
        )
        
    except Exception as e:
        payout.status = ShopPayout.STATUS_FAILED
        payout.error_message = str(e)
        payout.save()
        logger.error(f"PayPal Payout FAILED for payment {payment.id}: {e}")
    
    return payout
