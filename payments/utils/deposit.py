from decimal import Decimal

def calculate_deposit_details(shop, service, total_amount):
    """
    Calculates the deposit amount and determines if a deposit is required.
    
    Priority:
    1. Service-level overrides (is_deposit_required, deposit_type, etc.)
    2. Shop-level defaults (default_is_deposit_required, etc.)
    3. Fallback (20% if required but misconfigured)
    
    Returns:
        (is_deposit_required: bool, deposit_amount: Decimal)
    """
    is_deposit = False
    deposit_amount = total_amount # Default to full amount
    
    # 1. Check Service Level Logic
    if getattr(service, 'is_deposit_required', False):
        is_deposit = True
        deposit_type = getattr(service, 'deposit_type', None)
        
        if deposit_type == 'fixed':
            # Check if service has a specific deposit amount
            svc_deposit_amt = getattr(service, 'deposit_amount', None)
            if svc_deposit_amt:
                deposit_amount = Decimal(str(svc_deposit_amt))
            else:
                # Fallback: 20% if fixed type but no amount
                deposit_amount = (total_amount * Decimal('20')) / 100
                
        elif deposit_type == 'percentage':
            # Check if service has a specific percentage
            pct = getattr(service, 'deposit_percentage', None)
            if pct:
                deposit_amount = (total_amount * Decimal(pct)) / 100
            else:
                 # Fallback: 20%
                deposit_amount = (total_amount * Decimal('20')) / 100
        else:
             # Fallback if type is missing or invalid
             deposit_amount = (total_amount * Decimal('20')) / 100

    # 2. If Service didn't enforce it, check Shop default
    elif getattr(shop, 'default_is_deposit_required', False):
        is_deposit = True
        shop_def_type = getattr(shop, 'default_deposit_type', 'percentage')
        
        if shop_def_type == 'fixed':
            # Shop model might be missing default_deposit_amount, safely check
            def_val = getattr(shop, 'default_deposit_amount', None)
            if def_val:
                deposit_amount = Decimal(str(def_val))
            else:
                 # Fallback to 20% if fixed amount missing on Shop
                deposit_amount = (total_amount * Decimal('20')) / 100
                
        elif shop_def_type == 'percentage':
            pct = getattr(shop, 'default_deposit_percentage', 20) or 20
            deposit_amount = (total_amount * Decimal(pct)) / 100
        else:
            # Fallback
            deposit_amount = (total_amount * Decimal('20')) / 100
    
    else:
        # No deposit required at all
        deposit_amount = total_amount

    # Safety: Ensure we don't return None or exceed total
    if deposit_amount is None:
        deposit_amount = total_amount
        
    # Ensure precision is consistent (2 decimal places)
    deposit_amount = deposit_amount.quantize(Decimal("0.01"))
    
    # Final safety cap
    if deposit_amount > total_amount:
        deposit_amount = total_amount
        
    return is_deposit, deposit_amount
