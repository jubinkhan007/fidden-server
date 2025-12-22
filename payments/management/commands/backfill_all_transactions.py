"""
Backfill ALL missing TransactionLog entries for succeeded payments.

This is more comprehensive than backfill_checkout_transactions - it handles:
1. Deposits that never had TransactionLog created
2. Any other payment that is missing from TransactionLog

Run with --dry-run first to see what would be created.
"""
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from payments.models import Payment, TransactionLog
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Backfill ALL missing TransactionLog entries for succeeded payments"

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
        parser.add_argument(
            '--shop-id',
            type=int,
            help='Only process payments for a specific shop',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']
        shop_id = options.get('shop_id')

        self.stdout.write(f"{'[DRY RUN] ' if dry_run else ''}Starting comprehensive payment backfill...")

        # Find all succeeded payments
        payments_qs = Payment.objects.filter(
            status="succeeded"
        ).select_related('booking', 'booking__shop', 'booking__service', 'user')
        
        if shop_id:
            payments_qs = payments_qs.filter(booking__shop_id=shop_id)
            self.stdout.write(f"Filtering to shop_id={shop_id}")

        payments_qs = payments_qs[:limit]

        created_count = 0
        already_exists_count = 0
        error_count = 0

        for payment in payments_qs:
            try:
                # Check if TransactionLog already exists for this payment
                existing_logs = TransactionLog.objects.filter(
                    payment=payment,
                    transaction_type="payment"
                )
                
                if existing_logs.exists():
                    already_exists_count += 1
                    continue
                
                # Get amount - use deposit_paid for deposits, otherwise amount
                if payment.is_deposit and payment.deposit_paid:
                    amount = Decimal(str(payment.deposit_paid))
                else:
                    amount = Decimal(str(payment.amount or 0))
                
                if amount <= 0:
                    self.stdout.write(
                        self.style.WARNING(f"Payment {payment.id}: Amount is 0, skipping")
                    )
                    continue

                # Get booking info
                booking = payment.booking if hasattr(payment, 'booking') else None
                shop = booking.shop if booking else None
                
                if not shop:
                    self.stdout.write(
                        self.style.WARNING(f"Payment {payment.id}: No shop found, skipping")
                    )
                    continue

                if dry_run:
                    self.stdout.write(
                        f"[DRY RUN] Would create TransactionLog for Payment {payment.id}: "
                        f"${float(amount):.2f} (shop={shop.name}, created={payment.created_at})"
                    )
                    created_count += 1
                else:
                    with transaction.atomic():
                        TransactionLog.objects.create(
                            transaction_type="payment",
                            payment=payment,
                            user=payment.user,
                            shop=shop,
                            slot=booking,
                            service=booking.service if booking else None,
                            amount=amount,
                            currency=payment.currency or "usd",
                            status="succeeded",
                        )
                        created_count += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Created TransactionLog for Payment {payment.id}: ${float(amount):.2f}"
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
        self.stdout.write(f"  Already existed: {already_exists_count}")
        self.stdout.write(f"  Errors: {error_count}")

        if dry_run:
            self.stdout.write(self.style.WARNING("\nRun without --dry-run to apply changes."))
