"""
Backfill missing checkout TransactionLog entries.

For bookings that were completed before the P0-3 fix (ensure_checkout_transaction_logged),
this command creates the missing checkout TransactionLog entries.
"""
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from payments.models import Payment, TransactionLog, Booking
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Backfill missing checkout TransactionLog entries for completed bookings"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=1000,
            help='Maximum number of records to process (default: 1000)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']

        self.stdout.write(f"{'[DRY RUN] ' if dry_run else ''}Starting checkout transaction backfill...")

        # Find payments that:
        # 1. Have checkout_completed_at set (checkout was completed)
        # 2. Have balance_paid > 0 OR tips_amount > 0 (there was a checkout payment)
        # 3. Only have 1 TransactionLog entry (just the deposit, missing checkout)
        
        from django.db.models import Count, Q
        
        payments_with_checkout = Payment.objects.filter(
            checkout_completed_at__isnull=False
        ).filter(
            Q(balance_paid__gt=0) | Q(tips_amount__gt=0)
        ).annotate(
            tx_count=Count('transaction_logs', filter=Q(transaction_logs__transaction_type='payment'))
        ).filter(
            tx_count=1  # Only deposit log, missing checkout log
        )[:limit]

        created_count = 0
        skipped_count = 0
        error_count = 0

        for payment in payments_with_checkout:
            try:
                # Calculate checkout amount
                remaining = Decimal(str(payment.balance_paid or 0))
                tip = Decimal(str(payment.tips_amount or 0))
                checkout_amount = remaining + tip

                if checkout_amount <= 0:
                    skipped_count += 1
                    continue

                # Get booking for shop/slot info
                booking = getattr(payment, 'booking_record', None)
                if not booking:
                    self.stdout.write(
                        self.style.WARNING(f"Payment {payment.id}: No booking found, skipping")
                    )
                    skipped_count += 1
                    continue

                if dry_run:
                    self.stdout.write(
                        f"[DRY RUN] Would create TransactionLog for Payment {payment.id}: "
                        f"${float(checkout_amount):.2f} (remaining=${float(remaining):.2f}, tip=${float(tip):.2f})"
                    )
                    created_count += 1
                else:
                    with transaction.atomic():
                        TransactionLog.objects.create(
                            transaction_type="payment",
                            payment=payment,
                            user=payment.user,
                            shop=booking.shop,
                            slot=booking.slot if hasattr(booking, 'slot') else None,
                            service=booking.slot.service if hasattr(booking, 'slot') and booking.slot else None,
                            amount=checkout_amount,
                            currency=payment.currency or "usd",
                            status="succeeded",
                        )
                        created_count += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Created TransactionLog for Payment {payment.id}: ${float(checkout_amount):.2f}"
                            )
                        )

            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f"Payment {payment.id}: Error - {str(e)}")
                )
                logger.exception(f"Backfill error for payment {payment.id}")

        # Summary
        self.stdout.write("")
        self.stdout.write(f"{'[DRY RUN] ' if dry_run else ''}Backfill complete:")
        self.stdout.write(f"  Created: {created_count}")
        self.stdout.write(f"  Skipped: {skipped_count}")
        self.stdout.write(f"  Errors: {error_count}")

        if dry_run:
            self.stdout.write(self.style.WARNING("\nRun without --dry-run to apply changes."))
