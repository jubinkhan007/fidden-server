#!/usr/bin/env python
"""
Script to help shop owners set their niches correctly.
This allows updating a shop's niches (primary + capabilities).
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fidden.settings')
django.setup()

from api.models import Shop

def update_shop_niches(shop_id, niches):
    """
    Update a shop's niches.
    First niche = primary_niche
    Remaining = capabilities
    
    Args:
        shop_id: ID of the shop
        niches: List of niche strings, e.g., ["barber", "massage_therapist"]
    """
    try:
        shop = Shop.objects.get(id=shop_id)
        old_niches = shop.niches if shop.niches else []
        
        shop.niches = niches
        shop.save()
        
        print(f"✅ Updated Shop: {shop.name}")
        print(f"   Old niches: {old_niches}")
        print(f"   New niches: {niches}")
        print(f"   Primary: {shop.primary_niche}")
        print(f"   Capabilities: {niches[1:] if len(niches) > 1 else []}")
        
        return True
    except Shop.DoesNotExist:
        print(f"❌ Shop with ID {shop_id} not found")
        return False

def list_all_shops():
    """List all shops with their current niches"""
    shops = Shop.objects.all()
    
    print("\n" + "=" * 70)
    print("ALL SHOPS - NICHE CONFIGURATION")
    print("=" * 70)
    
    for shop in shops:
        print(f"\nShop ID: {shop.id}")
        print(f"Name: {shop.name}")
        print(f"Owner: {shop.owner.email if shop.owner else 'N/A'}")
        print(f"Niches: {shop.niches if shop.niches else 'Not set'}")
        print(f"Primary Niche: {shop.primary_niche}")
        print(f"Capabilities: {shop.niches[1:] if shop.niches and len(shop.niches) > 1 else []}")
        print("-" * 70)

def set_shop_to_barber(shop_id):
    """Quick helper to set a shop to Barber only"""
    return update_shop_niches(shop_id, ["barber"])

def set_shop_to_multi_niche(shop_id, primary, capabilities):
    """
    Quick helper for multi-niche shops
    
    Example:
        set_shop_to_multi_niche(1, "barber", ["massage_therapist", "esthetician"])
    """
    niches = [primary] + capabilities
    return update_shop_niches(shop_id, niches)

# Example usage:
if __name__ == "__main__":
    print("\n🛠️  NICHE MANAGEMENT TOOL")
    print("=" * 70)
    
    # List all shops
    list_all_shops()
    
    # Example: Update shop ID 1 to be a Barber
    # set_shop_to_barber(1)
    
    # Example: Update shop ID 2 to be Barber + Massage Therapist
    # set_shop_to_multi_niche(2, "barber", ["massage_therapist"])
    
    print("\n💡 To update a shop, uncomment the examples above or call:")
    print("   update_shop_niches(shop_id, ['barber', 'massage_therapist'])")
