from api.models import FitnessPackage

def decrement_fitness_package_sessions(booking):
    """
    If the booking belongs to a fitness trainer shop and the client has 
    an active fitness package at that shop, decrement the remaining sessions.
    """
    if not booking or not booking.shop or not booking.user:
        return

    # Check if shop is fitness trainer
    if 'fitness_trainer' not in (booking.shop.niches or []):
        if booking.shop.niche != 'fitness_trainer':
            return

    # Find the most recently created active package with sessions remaining
    package = FitnessPackage.objects.filter(
        shop=booking.shop,
        customer=booking.user,
        is_active=True,
        sessions_remaining__gt=0
    ).order_by('created_at').first()

    if package:
        package.sessions_remaining -= 1
        if package.sessions_remaining == 0:
            # Optionally mark as inactive if needed, but keeping it active 
            # might be better for history or till expiration
            pass
        package.save(update_fields=['sessions_remaining'])
        return True
    
    return False
