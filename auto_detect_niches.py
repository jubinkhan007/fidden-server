#!/usr/bin/env python
"""
Auto-detect and update shop niches based on their services.

This script analyzes each shop's services and automatically sets their niches.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fidden.settings')
django.setup()

from api.models import Shop

def update_all_shop_niches():
    """Update all shops with auto-detected niches"""
    shops = Shop.objects.all()
    updated_count = 0
    
    print("=" * 70)
    print("AUTO-DETECTING NICHES FROM SERVICES")
    print("=" * 70)
    
    for shop in shops:
        service_count = shop.services.count()
        old_niches = shop.niches if shop.niches else []
        
        # Auto-detect niches
        new_niches = shop.update_niches_from_services(save=True)
        
        print(f"\n Shop: {shop.name}")
        print(f"   ID: {shop.id}")
        print(f"   Services: {service_count}")
        print(f"   Old niches: {old_niches}")
        print(f"   New niches: {new_niches}")
        print(f"   Primary: {shop.primary_niche}")
        print(f"   Capabilities: {new_niches[1:] if len(new_niches) > 1 else []}")
        
        if old_niches != new_niches:
            updated_count += 1
            print(f"   ✅ Updated!")
        else:
            print(f"   ⏭️  No change")
    
    print("\n" + "=" * 70)
    print(f"COMPLETE: {updated_count}/{len(shops)} shops updated")
    print("=" * 70)

def show_detection_for_shop(shop_id):
    """Show what would be detected for a specific shop without saving"""
    try:
        shop = Shop.objects.get(id=shop_id)
        
        print(f"\nShop: {shop.name}")
        print(f"Services:")
        for service in shop.services.select_related('category').all():
            print(f"  - {service.title} (Category: {service.category.name if service.category else 'N/A'})")
        
        detected = shop.auto_detect_niches()
        print(f"\nDetected Niches: {detected}")
        print(f"Primary Niche: {detected[0] if detected else 'other'}")
        print(f"Capabilities: {detected[1:] if len(detected) > 1 else []}")
        
    except Shop.DoesNotExist:
        print(f"❌ Shop with ID {shop_id} not found")

if __name__ == "__main__":
    print("\n🔍 NICHE AUTO-DETECTION TOOL")
    print("=" * 70)
    
    # Update all shops
    update_all_shop_niches()
    
    # Example: Show detection for a specific shop
    # show_detection_for_shop(7)
