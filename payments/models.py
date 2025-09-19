from django.db import models
from django.conf import settings
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
import stripe

from api.models import Shop, SlotBooking

stripe.api_key = settings.STRIPE_SECRET_KEY  # Set this in your environment

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
# Payment for SlotBooking
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
                amount=int(self.payment.amount * 100),  # Stripe expects cents
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

                # Restore slot capacity
                slot_booking.slot.capacity_left += 1
                slot_booking.slot.save(update_fields=["capacity_left"])

                # Restore shop capacity
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
# Signals
# -----------------------------
# Create Stripe account when Shop is created
@receiver(post_save, sender=Shop)
def create_shop_stripe_account(sender, instance, created, **kwargs):
    if created:
        try:
            account = stripe.Account.create(
                type="express",
                email=instance.owner.email,
                business_type="individual",
                capabilities={
                    "card_payments": {"requested": True},
                    "transfers": {"requested": True},
                },
            )
            ShopStripeAccount.objects.create(shop=instance, stripe_account_id=account.id)
        except Exception as e:
            print(f"Stripe account creation failed for shop {instance.name}: {e}")

# Delete Stripe account when Shop is deleted
@receiver(post_delete, sender=Shop)
def delete_shop_stripe_account(sender, instance, **kwargs):
    if hasattr(instance, "stripe_account") and instance.stripe_account.stripe_account_id:
        try:
            stripe.Account.delete(instance.stripe_account.stripe_account_id)
        except Exception as e:
            print(f"Stripe account deletion failed for shop {instance.name}: {e}")

# Delete Stripe customer when User is deleted
from accounts.models import User
@receiver(post_delete, sender=User)
def delete_user_stripe_customer(sender, instance, **kwargs):
    if hasattr(instance, "stripe_customer") and instance.stripe_customer.stripe_customer_id:
        try:
            stripe.Customer.delete(instance.stripe_customer.stripe_customer_id)
        except Exception as e:
            print(f"Stripe customer deletion failed for user {instance.email}: {e}")

# Create Booking when Payment succeeds
@receiver(post_save, sender=Payment)
def create_booking_on_payment_success(sender, instance, created, **kwargs):
    if instance.status == "succeeded":
        # Ensure Booking not already created
        if not hasattr(instance, "booking_record"):
            try:
                Booking.objects.create(
                    payment=instance,
                    user=instance.user,
                    shop=instance.booking.shop,  # SlotBooking has relation with Shop
                    slot=instance.booking,
                    status="active",
                    stripe_payment_intent_id=instance.stripe_payment_intent_id
                )
            except Exception as e:
                print(f"Booking creation failed for payment {instance.id}: {e}")

@receiver(post_save, sender=Payment)
def log_successful_payment(sender, instance, created, **kwargs):
    """Create a transaction log automatically for successful payments."""
    if instance.status == "succeeded":
        if not TransactionLog.objects.filter(payment=instance, transaction_type="payment").exists():
            TransactionLog.objects.create(
                transaction_type="payment",
                payment=instance,
                user=instance.user,
                shop=instance.booking.shop if hasattr(instance, "booking") else None,
                slot=instance.booking if hasattr(instance, "booking") else None,
                service=instance.booking.service if hasattr(instance, "booking") else None,
                amount=instance.amount,
                currency=instance.currency,
                status=instance.status,
            )

@receiver(post_save, sender=Refund)
def log_successful_refund(sender, instance, created, **kwargs):
    """Create a transaction log automatically for successful refunds."""
    if instance.status == "succeeded":
        if not TransactionLog.objects.filter(refund=instance, transaction_type="refund").exists():
            TransactionLog.objects.create(
                transaction_type="refund",
                payment=instance.payment,
                refund=instance,
                user=instance.payment.user,
                shop=instance.payment.booking.shop if hasattr(instance.payment, "booking") else None,
                slot=instance.payment.booking if hasattr(instance.payment, "booking") else None,
                service=instance.payment.booking.service if hasattr(instance.payment, "booking") else None,
                amount=instance.amount,
                currency=instance.payment.currency,
                status=instance.status,
            )