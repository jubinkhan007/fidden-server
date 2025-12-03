
import os
import django
from datetime import timedelta, time
from django.utils import timezone
from decimal import Decimal

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fidden.settings')
django.setup()

from accounts.models import User
from api.models import Shop, Service, Slot, SlotBooking, BookingAddOn, ServiceCategory
from api.utils.slots import regenerate_slots_for_shop, generate_slots_for_service
from api.serializers import SlotBookingSerializer

def run_verification():
    print("Starting Verification...")
    
    # 1. Setup Data
    # Create Owner
    owner, _ = User.objects.get_or_create(email="owner@test.com", defaults={'role': 'owner'})
    
    # Create Shop
    shop, _ = Shop.objects.get_or_create(
        name="Test Shop", 
        owner=owner,
        defaults={
            'start_at': time(9, 0),
            'close_at': time(17, 0),
            'business_hours': {},
            'close_days': []
        }
    )
    
    # Create Category
    category, _ = ServiceCategory.objects.get_or_create(name="Test Category")

    # Create Services
    service_main, _ = Service.objects.get_or_create(
        shop=shop, 
        title="Main Service", 
        defaults={
            'duration': 60, 
            'price': Decimal("100.00"), 
            'capacity': 1,
            'category': category
        }
    )
    service_addon, _ = Service.objects.get_or_create(
        shop=shop, 
        title="Add-on Service", 
        defaults={
            'duration': 30, 
            'price': Decimal("50.00"), 
            'capacity': 1,
            'category': category
        }
    )
    
    # Ensure active
    service_main.is_active = True
    service_main.category = category # Ensure category is set if retrieved
    service_main.save()
    service_addon.is_active = True
    service_addon.category = category # Ensure category is set if retrieved
    service_addon.save()

    # Generate initial slots
    print("Generating initial slots...")
    regenerate_slots_for_shop(shop, days_ahead=2)
    
    # Use tomorrow to avoid "past slot" issues
    target_date = timezone.localdate() + timedelta(days=1)
    slots_target = Slot.objects.filter(shop=shop, start_time__date=target_date, service=service_main)
    print(f"Slots on target date: {slots_target.count()}")
    
    # 2. Test Real-time Slot Regeneration
    print("\n--- Testing Real-time Slot Regeneration ---")
    
    # Change Shop Hours to 10am - 4pm
    print("Changing shop hours to 10am - 4pm...")
    shop.start_at = time(10, 0)
    shop.close_at = time(16, 0)
    shop.save()
    
    # Trigger regeneration (simulating task)
    regenerate_slots_for_shop(shop, days_ahead=2)
    
    slots_new = Slot.objects.filter(shop=shop, start_time__date=target_date, service=service_main)
    print(f"Slots after update: {slots_new.count()}")
    
    # Verify 9am slot is gone
    nine_am = timezone.make_aware(timezone.datetime.combine(target_date, time(9, 0)))
    nine_am_slot = slots_new.filter(start_time=nine_am).exists()
    print(f"9am slot exists? {nine_am_slot} (Expected: False)")
    
    # 3. Test Add-on Booking
    print("\n--- Testing Add-on Booking ---")
    
    # Create User
    client, _ = User.objects.get_or_create(email="client@test.com")
    
    # Pick a slot (e.g., 10:00 AM)
    ten_am = timezone.make_aware(timezone.datetime.combine(target_date, time(10, 0)))
    slot_to_book = Slot.objects.filter(shop=shop, service=service_main, start_time=ten_am).first()
    
    if not slot_to_book:
        print("ERROR: No 10am slot found!")
        return

    print(f"Booking slot at {slot_to_book.start_time} with add-on...")
    
    # Simulate Request
    class MockRequest:
        def __init__(self, user):
            self.user = user
            
    request = MockRequest(client)
    
    # Data for serializer
    data = {
        'slot_id': slot_to_book.id,
        'add_on_ids': [service_addon.id]
    }
    
    serializer = SlotBookingSerializer(data=data, context={'request': request})
    if serializer.is_valid():
        booking = serializer.save()
        print(f"Booking created: ID {booking.id}")
        print(f"Start Time: {booking.start_time}")
        print(f"End Time: {booking.end_time}")
        
        expected_duration = service_main.duration + service_addon.duration # 60 + 30 = 90
        actual_duration = (booking.end_time - booking.start_time).total_seconds() / 60
        print(f"Duration: {actual_duration} mins (Expected: {expected_duration})")
        
        # Verify Add-on record
        addon_record = BookingAddOn.objects.filter(booking=booking, service=service_addon).first()
        if addon_record:
            print(f"Add-on record found: {addon_record}")
            print(f"Add-on price snapshot: {addon_record.price}")
        else:
            print("ERROR: Add-on record NOT found!")
            
    else:
        print(f"Validation Error: {serializer.errors}")

    # 4. Test Conflict Preservation
    print("\n--- Testing Conflict Preservation ---")
    # Now we have a booking at 10am.
    # Let's change shop hours to start at 12pm (making 10am invalid).
    print("Changing shop hours to 12pm - 4pm...")
    shop.start_at = time(12, 0)
    shop.save()
    
    regenerate_slots_for_shop(shop, days_ahead=2)
    
    # Verify the booked 10am slot still exists
    booked_slot = Slot.objects.filter(id=slot_to_book.id).first()
    print(f"Booked 10am slot exists? {booked_slot is not None} (Expected: True)")
    
    # Verify unbooked 11am slot is gone (if it existed)
    eleven_am = timezone.make_aware(timezone.datetime.combine(target_date, time(11, 0)))
    eleven_am_slot = Slot.objects.filter(shop=shop, service=service_main, start_time=eleven_am).exists()
    print(f"Unbooked 11am slot exists? {eleven_am_slot} (Expected: False)")

if __name__ == "__main__":
    run_verification()
