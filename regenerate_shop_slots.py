#!/usr/bin/env python
"""
Script to regenerate slots for a shop after timezone fix.
Run from Dokploy terminal or locally:
    python regenerate_shop_slots.py <shop_id>
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fidden.settings')
django.setup()

from api.models import Shop, Slot
from api.utils.slots import regenerate_slots_for_shop
from django.utils import timezone

def main():
    if len(sys.argv) < 2:
        print("Usage: python regenerate_shop_slots.py <shop_id>")
        print("\nAvailable shops:")
        for shop in Shop.objects.all()[:10]:
            print(f"  ID: {shop.id} - {shop.name} (timezone: {shop.time_zone})")
        return

    shop_id = int(sys.argv[1])
    
    try:
        shop = Shop.objects.get(id=shop_id)
    except Shop.DoesNotExist:
        print(f"Shop with ID {shop_id} not found!")
        return
    
    print(f"\n{'='*60}")
    print(f"Shop: {shop.name} (ID: {shop.id})")
    print(f"Timezone: {shop.time_zone}")
    print(f"Working Hours: {shop.start_at} - {shop.close_at}")
    print(f"{'='*60}\n")
    
    # Count slots before
    future_slots = Slot.objects.filter(shop=shop, start_time__gte=timezone.now())
    print(f"Future slots before regeneration: {future_slots.count()}")
    
    # Sample of current slots (first 5)
    print("\nSample of current slots (UTC times):")
    for slot in future_slots.order_by('start_time')[:5]:
        print(f"  {slot.start_time} - {slot.end_time}")
    
    # Confirm
    confirm = input("\nRegenerate slots? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Aborted.")
        return
    
    # Regenerate
    print("\nRegenerating slots...")
    regenerate_slots_for_shop(shop, days_ahead=14)
    
    # Count slots after
    new_slots = Slot.objects.filter(shop=shop, start_time__gte=timezone.now())
    print(f"\nFuture slots after regeneration: {new_slots.count()}")
    
    # Sample of new slots
    print("\nSample of NEW slots (UTC times):")
    for slot in new_slots.order_by('start_time')[:5]:
        print(f"  {slot.start_time} - {slot.end_time}")
    
    print("\n✅ Slots regenerated! Refresh the app to see new times.")

if __name__ == "__main__":
    main()
