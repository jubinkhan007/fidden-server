from django.contrib import admin
from .models import SubscriptionPlan, ShopSubscription

@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'monthly_price', 'commission_rate', 'stripe_price_id')
    
@admin.register(ShopSubscription)
class ShopSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('shop', 'plan', 'status', 'start_date', 'end_date', 'stripe_subscription_id')
    list_filter = ('plan', 'status')
    search_fields = ('shop__name', 'stripe_subscription_id')
    readonly_fields = ('start_date', 'end_date')