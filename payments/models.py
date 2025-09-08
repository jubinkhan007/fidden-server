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
