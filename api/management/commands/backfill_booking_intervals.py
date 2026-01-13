from django.core.management.base import BaseCommand
from django.utils import timezone
from payments.models import Booking
from api.models import Service
from datetime import timedelta

class Command(BaseCommand):
    help = 'Backfills provider_busy_start/end and processing_start/end for legacy bookings based on Service definitions.'

    def handle(self, *args, **options):
        self.stdout.write("Starting backfill of booking intervals...")
        
        # Only process active/confirmed bookings in the future or recent past (optimization)
        # For safety, let's look at everything from today onwards, or even last 30 days.
        cutoff = timezone.now() - timedelta(days=30)
        bookings = Booking.objects.filter(
            status__in=['active'],
            slot__start_time__gte=cutoff,
            provider_busy_start__isnull=True
        ).select_related('slot__service', 'slot')
        
        updated_count = 0
        
        for booking in bookings:
            # Booking -> SlotBooking -> Service
            service = booking.slot.service
            start_time = booking.slot.start_time
            
            if not service:
                self.stdout.write(self.style.WARNING(f"Booking {booking.id} has no service. Skipping."))
                continue
                
            # Calculate intervals logic (mirroring Availability Engine logic)
            duration = service.duration or 30
            block_mins = service.provider_block_minutes if service.provider_block_minutes is not None else duration
            
            # Busy Start is simple: start_time
            # Busy End is: start_time + block_mins
            
            busy_start = start_time
            busy_end = start_time + timedelta(minutes=block_mins)
            
            booking.provider_busy_start = busy_start
            booking.provider_busy_end = busy_end
            
            # Processing: only if allow_processing_overlap is True AND block < duration
            if service.allow_processing_overlap and block_mins < duration:
                # Processing IS the remainder
                booking.processing_start = busy_end
                booking.processing_end = start_time + timedelta(minutes=duration)
            else:
                booking.processing_start = None
                booking.processing_end = None
                
            booking.save(update_fields=['provider_busy_start', 'provider_busy_end', 'processing_start', 'processing_end'])
            updated_count += 1
            
            if updated_count % 100 == 0:
                 self.stdout.write(f"Processed {updated_count} bookings...")
                 
        self.stdout.write(self.style.SUCCESS(f"Successfully backfilled {updated_count} bookings."))
