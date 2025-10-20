from datetime import timedelta
import os
from django.db import models
from django.conf import settings
from django.db.models import F
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
import stripe
from django.core.mail import send_mail
from accounts.models import User
from api.models import AutoFillLog, Shop, SlotBooking, Revenue, Coupon
from api.utils.fcm import notify_user
import logging
import traceback
from django.apps import apps as django_apps

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY

# -----------------------------
# Shop Stripe Account
# -----------------------------
class ShopStripeAccount(models.Model):
    shop = models.OneToOneField(Shop, on_delete=models.CASCADE, related_name='stripe_account')
    stripe_account_id = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.shop.name} Stripe Account"

# -----------------------------
# User Stripe Customer
# -----------------------------
class UserStripeCustomer(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='stripe_customer')
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} Stripe Customer"

# -----------------------------
# Payment Table
# -----------------------------
class Payment(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
        ("refunded", "Refunded"),
    ]

    booking = models.OneToOneField(SlotBooking, on_delete=models.CASCADE, related_name='payment')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    is_deposit = models.BooleanField(default=False)
    remaining_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    # Amount that has been actually paid toward the booking's balance (defaults 0).
    balance_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deposit_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_type = models.CharField(max_length=20, default='full')
    tips_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    application_fee_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, blank=True, null=True, related_name='payment_coupon',
        help_text="Coupon applied to this payment"
    )
    coupon_amount = models.DecimalField( max_digits=10, decimal_places=2, blank=True, null=True,
        help_text="Amount after applying coupon discount (if any)"
    )
    currency = models.CharField(max_length=10, default="usd")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payment #{self.pk}"

# -----------------------------
# Refund Table
# -----------------------------
class Refund(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
    ]

    payment = models.OneToOneField(Payment, on_delete=models.CASCADE, related_name="refund")
    stripe_refund_id = models.CharField(max_length=255, blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    reason = models.CharField(max_length=255, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Refund #{self.pk} for Payment #{self.payment_id}"

# -----------------------------
# Booking Table
# -----------------------------
class Booking(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
        # --- NEW STATUSES ---
        ("no-show", "No-Show"),
        ("late-cancel", "Late Cancel"),
        ('no-show', 'No-Show'),
    ]

    payment = models.OneToOneField(Payment, on_delete=models.CASCADE, related_name="booking_record")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE)
    slot = models.ForeignKey(SlotBooking, on_delete=models.CASCADE)
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Booking {self.id} - {self.status}"

    def cancel_booking(self, reason="requested_by_customer"):
        """Cancel booking, refund payment, and update linked SlotBooking"""
        if self.status == "cancelled":
            return False, "Booking already cancelled"

        try:
            # Calculate refund amount based on cancellation policy
            hours_before_booking = (self.slot.start_time - timezone.now()).total_seconds() / 3600
            refund_amount = 0
            if hours_before_booking > self.shop.free_cancellation_hours:
                refund_amount = self.payment.amount
            elif hours_before_booking > self.shop.no_refund_hours:
                refund_amount = self.payment.amount * (100 - self.shop.cancellation_fee_percentage) / 100

            # 1️⃣ Refund payment via Stripe
            if refund_amount > 0:
                refund = stripe.Refund.create(
                    payment_intent=self.stripe_payment_intent_id,
                    amount=int(refund_amount * 100),
                    reason=reason,
                )

                # 2️⃣ Save refund record
                Refund.objects.create(
                    payment=self.payment,
                    stripe_refund_id=refund.id,
                    amount=refund_amount,
                    status=refund.status,
                    reason=reason,
                )

            # 3️⃣ Update booking status
            self.status = "cancelled"
            self.save(update_fields=["status", "updated_at"])

            # 4️⃣ Update payment status
            self.payment.status = "refunded" if refund_amount > 0 else "failed"
            self.payment.save(update_fields=["status", "updated_at"])

            # 5️⃣ Cancel linked SlotBooking and update capacities
            slot_booking: SlotBooking = self.slot
            if slot_booking.status != "cancelled":
                slot_booking.status = "cancelled"
                slot_booking.save(update_fields=["status"])

                slot_booking.payment_status = "refund"
                slot_booking.save(update_fields=["payment_status"])

                slot_booking.slot.capacity_left += 1
                slot_booking.slot.save(update_fields=["capacity_left"])

                slot_booking.shop.capacity += 1
                slot_booking.shop.save(update_fields=["capacity"])

            return True, f"Refund processed and booking cancelled successfully"
        except Exception as e:
            return False, str(e)

# -----------------------------
# Transaction Log Table
# -----------------------------
class TransactionLog(models.Model):
    TRANSACTION_TYPE_CHOICES = [
        ("payment", "Payment"),
        ("refund", "Refund"),
    ]

    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPE_CHOICES)
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="transaction_logs")
    refund = models.ForeignKey(Refund, on_delete=models.CASCADE, null=True, blank=True, related_name="transaction_logs")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE)
    slot = models.ForeignKey('api.SlotBooking', on_delete=models.CASCADE, null=True, blank=True)
    service = models.ForeignKey('api.Service', on_delete=models.CASCADE, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default="usd")
    status = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.transaction_type.capitalize()} {self.id} - {self.status} - {self.amount} {self.currency}"

# -----------------------------
# CouponUsage Table
# -----------------------------
class CouponUsage(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='coupon_usages')
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name='usages')
    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-used_at']
        indexes = [
            models.Index(fields=['user', 'coupon']),
        ]

    def __str__(self):
        return f"{self.user} used {self.coupon.code} at {self.used_at}"

# -----------------------------
# Helper Function
# -----------------------------
def can_use_coupon(user, coupon):
    """
    Check if a user can use the coupon based on max_usage_per_user.
    Returns True if allowed, False otherwise.
    """
    used_count = CouponUsage.objects.filter(user=user, coupon=coupon).count()
    if not coupon.is_active:
        return False
    if coupon.max_usage_per_user is None:
        return True  # unlimited usage
    return used_count < coupon.max_usage_per_user

# -----------------------------
# Signals
# -----------------------------

# Stripe account for Shop
@receiver(post_save, sender=Shop)
def create_shop_stripe_account(sender, instance, created, **kwargs):
    if created:
        try:
            account = stripe.Account.create(
                type="express",
                email=instance.owner.email,
                business_type="individual",
                capabilities={"card_payments": {"requested": True}, "transfers": {"requested": True}},
            )
            ShopStripeAccount.objects.create(shop=instance, stripe_account_id=account.id)
        except Exception as e:
            print(f"Stripe account creation failed for shop {instance.name}: {e}")

@receiver(post_delete, sender=Shop)
def delete_shop_stripe_account(sender, instance, **kwargs):
    if hasattr(instance, "stripe_account") and instance.stripe_account.stripe_account_id:
        try:
            stripe.Account.delete(instance.stripe_account.stripe_account_id)
        except Exception as e:
            print(f"Stripe account deletion failed for shop {instance.name}: {e}")

@receiver(post_delete, sender=User)
def delete_user_stripe_customer(sender, instance, **kwargs):
    if hasattr(instance, "stripe_customer") and instance.stripe_customer.stripe_customer_id:
        try:
            stripe.Customer.delete(instance.stripe_customer.stripe_customer_id)
        except Exception as e:
            print(f"Stripe customer deletion failed for user {instance.email}: {e}")

# Payment post_save: handle succeeded and refunded
@receiver(post_save, sender=Payment)
def handle_payment_status(sender, instance, created, **kwargs):
    try:
        slot_booking = instance.booking 
        shop = slot_booking.shop

        # ---------------- Payment Succeeded ----------------
        if instance.status == "succeeded":
            # Update SlotBooking payment status
            if slot_booking.payment_status != "success":
                slot_booking.payment_status = "success"
                slot_booking.save(update_fields=["payment_status"])
                    
            # Create Booking if not exists
            # Create Booking exactly once for this Payment
            booking_obj, created_booking = Booking.objects.get_or_create(
                payment=instance,
                defaults={
                    "user": instance.user,
                    "shop": instance.booking.shop,
                    "slot": instance.booking,
                    "status": "active",
                    "stripe_payment_intent_id": instance.stripe_payment_intent_id,
                },
            )

            # ---- Close the AutoFillLog loop if this booking filled an offer (with DEBUG logs) ----
            AutoFillLog = django_apps.get_model("api", "AutoFillLog")

            slot_booking = instance.booking          # payments.SlotBooking
            shop = slot_booking.shop
            slot_obj = getattr(slot_booking, "slot", None)  # api.Slot or None
            slot_id = getattr(slot_obj, "id", None)
            service_id = getattr(slot_booking, "service_id", None)

            ai_settings = getattr(shop, "ai_settings", None)
            scope_hours = getattr(ai_settings, "auto_fill_scope_hours", 48) or 48
            window_start = timezone.now() - timedelta(hours=scope_hours)

            logger.info(
                "[AutoFillClose] payment_id=%s booking_obj_id=%s shop_id=%s service_id=%s "
                "slotbooking_id=%s slot_id=%s window_start=%s",
                instance.id, booking_obj.id, shop.id, service_id, slot_booking.id, slot_id, window_start.isoformat()
            )

            # 1) Prefer exact offered slot match (AutoFillLog.offered_slot == this SlotBooking.slot)
            exact_qs = (
                AutoFillLog.objects
                .filter(
                    shop=shop,
                    status__in=("initiated", "outreach_started"),
                    created_at__gte=window_start,
                    offered_slot=slot_obj,  # precise match
                )
                .order_by("-created_at")
            )

            exact_ids = list(exact_qs.values_list("id", flat=True)[:10])
            logger.info(
                "[AutoFillClose] exact_match_candidates=%s ids=%s (showing up to 10)",
                exact_qs.count(), exact_ids
            )

            log_to_close = exact_qs.first()

            # 2) Fallback: any open log for the same service in window (covers “offer original slot” and older logs)
            if not log_to_close:
                fallback_qs = (
                    AutoFillLog.objects
                    .select_related("original_booking")
                    .filter(
                        shop=shop,
                        status__in=("initiated", "outreach_started"),
                        created_at__gte=window_start,
                        original_booking__slot__service_id=service_id,
                    )
                    .order_by("-created_at")
                )
                fallback_ids = list(fallback_qs.values_list("id", flat=True)[:10])
                logger.info(
                    "[AutoFillClose] fallback_candidates=%s ids=%s (showing up to 10)",
                    fallback_qs.count(), fallback_ids
                )
                log_to_close = fallback_qs.first()

            if log_to_close:
                logger.info(
                    "[AutoFillClose] MATCHED log_id=%s (offered_slot_id=%s, status=%s). Completing...",
                    log_to_close.id,
                    getattr(log_to_close.offered_slot, "id", None),
                    log_to_close.status,
                )
                fields = ["filled_by_booking", "status"]
                log_to_close.filled_by_booking = booking_obj
                log_to_close.status = "completed"
                recovered = getattr(instance, "amount", 0) or 0
                if recovered:
                    log_to_close.revenue_recovered = recovered
                    fields.append("revenue_recovered")
                log_to_close.save(update_fields=fields)
                logger.info(
                    "[AutoFillClose] COMPLETED log_id=%s set fields=%s recovered=%s",
                    log_to_close.id, fields, recovered
                )
            else:
                # Help debug by showing a few recent open logs for this shop
                recent_open = (
                    AutoFillLog.objects
                    .filter(shop=shop, status__in=("initiated", "outreach_started"))
                    .order_by("-created_at")[:5]
                )
                recent_dump = [
                    dict(
                        id=l.id,
                        created_at=l.created_at.isoformat(),
                        offered_slot_id=getattr(l.offered_slot, "id", None),
                        original_booking_id=getattr(l.original_booking, "id", None),
                        status=l.status,
                    )
                    for l in recent_open
                ]
                logger.warning(
                    "[AutoFillClose] NO MATCH. Inspect recent open logs for shop_id=%s: %s",
                    shop.id, recent_dump
                )

            # Update SlotBooking payment status (safe to run multiple times)
            slot_booking = instance.booking
            if slot_booking.payment_status != "success":
                slot_booking.payment_status = "success"
                slot_booking.save(update_fields=["payment_status"])


            if created_booking:
                try:
                    start_time = timezone.localtime(slot_booking.start_time).strftime("%A, %d %B %Y at %I:%M %p")
                    end_time = timezone.localtime(slot_booking.end_time).strftime("%I:%M %p")
                    shop_name = shop.name
                    service_title = slot_booking.service.title
                    customer_name = instance.user.name or instance.user.email

                    from_email = settings.DEFAULT_FROM_EMAIL
                    to_email = [slot_booking.shop.owner.email]
                    subject = "New Appointment Booked"

                    owner_message = (
                        f"Hello {slot_booking.shop.owner.name or 'Shop Owner'},\n\n"
                        f"A new appointment has been booked.\n\n"
                        f"👤 Customer: {customer_name}\n"
                        f"🏬 Shop: {shop_name}\n"
                        f"💆 Service: {service_title}\n"
                        f"🗓 Date & Time: {start_time} – {end_time}\n\n"
                        f"Please prepare accordingly."
                    )

                    send_mail(subject, owner_message, from_email, to_email)
                except Exception as email_error:
                    logger.error(
                        "Failed to send email to shop owner %s: %s\n%s",
                        shop.owner.id if shop.owner else "unknown",
                        str(email_error),
                        traceback.format_exc()
                    )

                try:
                    #  Push notification to shop owner
                    notify_user(
                        shop.owner,
                        message=(
                            f"New appointment from {customer_name} for {service_title} "
                            f"on {start_time}."
                        ),
                        notification_type="booking",
                        data={
                            "shop_id": shop.id,
                            "booking_id": slot_booking.id,
                            "service": service_title,
                            "start_time": str(slot_booking.start_time),
                            "end_time": str(slot_booking.end_time),
                        },
                        debug=True
                    )
                except Exception as notify_error:
                    logger.error(
                        "Failed to send push notification to shop owner %s: %s\n%s",
                        shop.owner.id if shop.owner else "unknown",
                        str(notify_error),
                        traceback.format_exc()
                    )
            # Create payment TransactionLog if not exists
            if not TransactionLog.objects.filter(payment=instance, transaction_type="payment").exists():
                TransactionLog.objects.get_or_create(
                transaction_type="payment",
                payment=instance,
                defaults={
                    "user": instance.user,
                    "shop": instance.booking.shop,
                    "slot": instance.booking,
                    "service": instance.booking.service,
                    "amount": instance.amount,
                    "currency": instance.currency,
                    "status": instance.status,
                },
            )
        # ---------------- Payment Refunded ----------------
        elif instance.status == "refunded":
            if hasattr(instance, "booking_record"):
                booking = instance.booking_record
                if booking.status != "cancelled":
                    booking.status = "cancelled"
                    booking.save(update_fields=["status", "updated_at"])

            refund = getattr(instance, "refund", None)
            if refund and not TransactionLog.objects.filter(refund=refund, transaction_type="refund").exists():
                TransactionLog.objects.create(
                    transaction_type="refund",
                    payment=instance,
                    refund=refund,
                    user=instance.user,
                    shop=instance.booking.shop if hasattr(instance, "booking_record") else None,
                    slot=instance.booking if hasattr(instance, "booking_record") else None,
                    service=instance.booking.service if hasattr(instance, "booking_record") else None,
                    amount=refund.amount,
                    currency=instance.currency,
                    status=refund.status,
                )
    except Exception as e:
        logger.error(
            "Payment signal error for Payment %s: %s\n%s",
            instance.id,
            str(e),
            traceback.format_exc()
        )

# Refund post_save (optional: for direct Stripe refunds)
@receiver(post_save, sender=Refund)
def log_refund_transaction(sender, instance, created, **kwargs):
    if instance.status == "succeeded":
        if not TransactionLog.objects.filter(refund=instance, transaction_type="refund").exists():
            TransactionLog.objects.create(
                transaction_type="refund",
                payment=instance.payment,
                refund=instance,
                user=instance.payment.user,
                shop=instance.payment.booking_record.shop if hasattr(instance.payment, "booking_record") else None,
                slot=instance.payment.booking_record.slot if hasattr(instance.payment, "booking_record") else None,
                service=instance.payment.booking_record.slot.service if hasattr(instance.payment, "booking_record") and instance.payment.booking_record.slot else None,
                amount=instance.amount,
                currency=instance.payment.currency,
                status=instance.status,
            )

# Update Daily Revenue
@receiver(post_save, sender=TransactionLog)
def update_daily_revenue(sender, instance, created, **kwargs):
    """
    Update or create daily revenue for the shop whenever a transaction log is added.
    - Payment -> add amount
    - Refund -> subtract amount
    - One row per shop per day
    """
    if not created:
        return  # Only act on newly created transaction logs

    shop = instance.shop
    transaction_date = instance.created_at.date()
    amount = instance.amount

    # Determine revenue delta: + for payment, - for refund
    delta = amount if instance.transaction_type == "payment" else -amount

    # Try to get today's revenue row
    revenue_obj = Revenue.objects.filter(shop=shop, timestamp=transaction_date).first()

    if revenue_obj:
        # Update existing revenue
        Revenue.objects.filter(pk=revenue_obj.pk).update(revenue=F('revenue') + delta)
    else:
        # Create new revenue row for today
        Revenue.objects.create(shop=shop, timestamp=transaction_date, revenue=delta)
