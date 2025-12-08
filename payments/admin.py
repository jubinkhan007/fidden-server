# payments/admin.py

from django.contrib import admin
from .models import (
    ShopStripeAccount, 
    UserStripeCustomer, 
    Payment, 
    Booking,
    Refund,
    TransactionLog,
    CouponUsage,
    ShopPayout,
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

# -----------------------------
# Booking Admin
# -----------------------------
@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("id", "payment", "user", "shop", "slot", "status", "created_at", "updated_at")
    list_filter = ("status", "created_at")
    search_fields = ("user__email", "shop__name")
    readonly_fields = ("created_at", "updated_at")
    actions = ['mark_as_no_show', 'mark_as_late_cancel']


# -----------------------------
# Refund Admin
# -----------------------------
@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ("id", "payment", "amount", "status", "reason", "created_at", "updated_at")
    list_filter = ("status",)
    search_fields = ("stripe_refund_id", "payment__id")
    readonly_fields = ("created_at", "updated_at")

# -----------------------------
# TransactionLog Admin
# -----------------------------
@admin.register(TransactionLog)
class TransactionLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "transaction_type",
        "payment",
        "refund",
        "user",
        "shop",
        "slot",
        "service",
        "amount",
        "currency",
        "status",
        "created_at",
    )
    list_filter = ("transaction_type", "status", "currency")
    search_fields = (
        "payment__id",
        "refund__stripe_refund_id",
        "user__username",
        "shop__name",
        "slot__id",
        "service__title",
    )
    readonly_fields = ("created_at",)

@admin.register(CouponUsage)
class CouponUsageAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'coupon', 'used_at')
    list_filter = ('coupon', 'used_at')
    search_fields = ('user__username', 'coupon__code')
    ordering = ('-used_at',)

# -----------------------------
# ShopPayout Admin (PayPal → Stripe Transfer)
# -----------------------------
@admin.register(ShopPayout)
class ShopPayoutAdmin(admin.ModelAdmin):
    list_display = (
        "id", 
        "shop", 
        "gross_amount", 
        "commission_amount", 
        "net_amount", 
        "commission_rate",
        "status", 
        "created_at",
        "completed_at",
    )
    list_filter = ("status", "created_at", "shop")
    search_fields = ("shop__name", "stripe_transfer_id", "payment__stripe_payment_intent_id")
    readonly_fields = ("stripe_transfer_id", "created_at", "completed_at", "error_message")
    raw_id_fields = ("shop", "payment")
    
    actions = ["retry_failed_payouts"]
    
    @admin.action(description="Retry failed payouts (transfer to Stripe)")
    def retry_failed_payouts(self, request, queryset):
        from payments.utils.payouts import process_shop_payout
        failed = queryset.filter(status=ShopPayout.STATUS_FAILED)
        success_count = 0
        for payout in failed:
            new_payout = process_shop_payout(payout.payment)
            if new_payout.status == ShopPayout.STATUS_COMPLETED:
                success_count += 1
        self.message_user(request, f"Retried {failed.count()} payouts. {success_count} succeeded.")