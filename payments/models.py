import os
from django.db import models
from django.conf import settings
from django.db.models import F
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
import stripe
from django.core.mail import send_mail
from api.models import Shop, SlotBooking, Revenue, Coupon

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
        return f"Payment {self.id} for {self.booking}"

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
        return f"Refund {self.id} for Payment {self.payment_id}"

# -----------------------------
# Booking Table
# -----------------------------
class Booking(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
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
            # 1️⃣ Refund payment via Stripe
            refund = stripe.Refund.create(
                payment_intent=self.stripe_payment_intent_id,
                amount=int(self.payment.amount * 100),
                reason=reason,
            )

            # 2️⃣ Save refund record
            Refund.objects.create(
                payment=self.payment,
                stripe_refund_id=refund.id,
                amount=self.payment.amount,
                status=refund.status,
                reason=reason,
            )

            # 3️⃣ Update booking status
            self.status = "cancelled"
            self.save(update_fields=["status", "updated_at"])

            # 4️⃣ Update payment status
            self.payment.status = "refunded" if refund.status in ["succeeded", "pending"] else "failed"
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

            return True, f"Refund {refund.status} and booking cancelled successfully"
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

# Stripe customer for User
from accounts.models import User

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
        slot_booking = instance.booking  # Direct OneToOne relation
        shop = slot_booking.shop

        # ---------------- Payment Succeeded ----------------
        if instance.status == "succeeded":
            if instance.status == "succeeded":
                # Update SlotBooking payment status
                if slot_booking.payment_status != "success":
                    slot_booking.payment_status = "success"
                    slot_booking.save(update_fields=["payment_status"])
                    
            # Create Booking if not exists
            if not hasattr(instance, "booking_record"):
                Booking.objects.create(
                    payment=instance,
                    user=instance.user,
                    shop=instance.booking.shop,
                    slot=instance.booking,
                    status="active",
                    stripe_payment_intent_id=instance.stripe_payment_intent_id
                )
                
            # ✅ Send personalized reminder email to SHOP OWNER
            if shop and shop.owner and shop.owner.email:
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

            # Create payment TransactionLog if not exists
            if not TransactionLog.objects.filter(payment=instance, transaction_type="payment").exists():
                TransactionLog.objects.create(
                    transaction_type="payment",
                    payment=instance,
                    user=instance.user,
                    shop=instance.booking.shop,
                    slot=instance.booking,
                    service=instance.booking.service,
                    amount=instance.amount,
                    currency=instance.currency,
                    status=instance.status,
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
        print(f"Payment signal error for Payment {instance.id}: {e}")

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

