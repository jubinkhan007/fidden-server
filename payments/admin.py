# payments/admin.py

from django.contrib import admin
from .models import (
    ShopStripeAccount, 
    UserStripeCustomer, 
    Payment, 
    Booking
)

# -----------------------------
# ShopStripeAccount Admin
# -----------------------------
@admin.register(ShopStripeAccount)
class ShopStripeAccountAdmin(admin.ModelAdmin):
    list_display = ("shop", "stripe_account_id", "created_at")
    search_fields = ("shop__name", "stripe_account_id")
    readonly_fields = ("created_at",)

# -----------------------------
# UserStripeCustomer Admin
# -----------------------------
@admin.register(UserStripeCustomer)
class UserStripeCustomerAdmin(admin.ModelAdmin):
    list_display = ("user", "stripe_customer_id", "created_at")
    search_fields = ("user__email", "stripe_customer_id")
    readonly_fields = ("created_at",)

# -----------------------------
# Payment Admin
# -----------------------------
@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "booking", "user", "amount", "currency", "status", "created_at", "updated_at")
    list_filter = ("status", "currency", "created_at")
    search_fields = ("booking__id", "user__email", "stripe_payment_intent_id")
    readonly_fields = ("created_at", "updated_at", "stripe_payment_intent_id")

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("id", "payment", "user", "shop", "slot", "status", "created_at", "updated_at")
    list_filter = ("status", "created_at")
    search_fields = ("user__email", "shop__name")
    readonly_fields = ("created_at", "updated_at")
