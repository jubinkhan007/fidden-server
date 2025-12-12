"""
Fidden Pay - Tip and Commission Utilities
"""
from decimal import Decimal


def calculate_tip(service_price: Decimal, tip_option: str, custom_amount: Decimal = None) -> Decimal:
    """
    Calculate tip amount based on the selected option.
    Tip is calculated on FULL service price per Fidden Pay spec.
    
    Args:
        service_price: Full service price (tip base)
        tip_option: '10', '15', '20', or 'custom'
        custom_amount: Dollar amount if tip_option is 'custom'
    
    Returns:
        Decimal: Tip amount
    """
    if tip_option == 'custom':
        return Decimal(str(custom_amount or 0))
    
    rates = {
        '10': Decimal('0.10'),
        '15': Decimal('0.15'),
        '20': Decimal('0.20'),
    }
    rate = rates.get(tip_option, Decimal('0'))
    return (service_price * rate).quantize(Decimal('0.01'))


def get_tip_percent(service_price: Decimal, tip_amount: Decimal) -> Decimal:
    """
    Calculate tip percentage from tip amount.
    """
    if service_price == 0:
        return Decimal('0')
    return (tip_amount / service_price).quantize(Decimal('0.0001'))


def calculate_commission(service_price: Decimal, subscription) -> Decimal:
    """
    Calculate Fidden commission based on subscription plan.
    Commission = 10% of service_price (Foundation only), excludes tips.
    
    Args:
        service_price: Full service price
        subscription: ShopSubscription object
    
    Returns:
        Decimal: Commission amount
    """
    if not subscription or not subscription.plan:
        # Default to Foundation (10%)
        return (service_price * Decimal('0.10')).quantize(Decimal('0.01'))
    
    plan_name = subscription.plan.name
    if plan_name == 'Foundation':
        commission_rate = subscription.plan.commission_rate / 100
        return (service_price * commission_rate).quantize(Decimal('0.01'))
    
    # Momentum and Icon = 0% commission
    return Decimal('0')
