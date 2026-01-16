from django.core.management.base import BaseCommand
from api.models import Shop

class Command(BaseCommand):
    help = 'Forces all shops to require deposits'

    def handle(self, *args, **options):
        # Update all shops to require deposits
        updated_count = Shop.objects.update(default_is_deposit_required=True)
        
        # Also ensure they have a valid deposit type (fallback to percentage if missing)
        Shop.objects.filter(default_deposit_type__isnull=True).update(default_deposit_type='percentage')
        
        # Ensure percentage is set
        Shop.objects.filter(default_deposit_percentage__isnull=True).update(default_deposit_percentage=20)

        self.stdout.write(self.style.SUCCESS(f'Successfully updated {updated_count} shops to require deposits.'))
