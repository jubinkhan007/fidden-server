from django.core.management.base import BaseCommand
from api.models import Shop

class Command(BaseCommand):
    help = 'Auto-verifies all shops (sets status to "verified")'

    def handle(self, *args, **options):
        count = Shop.objects.exclude(status='verified').update(status='verified')
        self.stdout.write(self.style.SUCCESS(f'Successfully verified {count} shops.'))
