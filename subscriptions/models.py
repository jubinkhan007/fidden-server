from django.db import models
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from dateutil.relativedelta import relativedelta

class SubscriptionPlan(models.Model):
    """
    Represents a subscription tier (e.g., Foundation, Momentum, Icon).
    This model stores pricing, commissions, and feature entitlements for each plan.
    """
    # Plan Tiers
    FOUNDATION = "Foundation"
    MOMENTUM = "Momentum"
    ICON = "Icon"
    PLAN_CHOICES = [
        (FOUNDATION, "Foundation"),
        (MOMENTUM, "Momentum"),
        (ICON, "Icon"),
    ]

    # Feature Levels
    DEPOSIT_DEFAULT = "default"
    DEPOSIT_BASIC = "basic"
    DEPOSIT_ADVANCED = "advanced"
    DEPOSIT_CHOICES = [
        (DEPOSIT_DEFAULT, "Default only"),
        (DEPOSIT_BASIC, "Basic"),
        (DEPOSIT_ADVANCED, "Advanced"),
    ]

    AI_ADDON = "addon"
    AI_INCLUDED = "included"
    AI_CHOICES = [
        (AI_ADDON, "Add-on"),
        (AI_INCLUDED, "Included"),
    ]

    PERF_NONE = "none"
    PERF_BASIC = "basic"
    PERF_MODERATE = "moderate"  # New tier
    PERF_ADVANCED = "advanced"
    PERF_CHOICES = [
        (PERF_NONE, "None"),
        (PERF_BASIC, "Basic"),
        (PERF_MODERATE, "Moderate"),  # New tier
        (PERF_ADVANCED, "Advanced"),
    ]
    
    name = models.CharField(max_length=50, choices=PLAN_CHOICES, unique=True)
    monthly_price = models.DecimalField(max_digits=6, decimal_places=2)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, help_text="Percentage rate, e.g., 10.00 for 10%")
    stripe_price_id = models.CharField(max_length=100, blank=True, null=True, help_text="Stripe Price ID for this plan")

    # Features based on screenshot
    marketplace_profile = models.BooleanField(default=True)
    instant_booking_payments = models.BooleanField(default=True)
    automated_reminders = models.BooleanField(default=True)
    smart_rebooking_prompts = models.BooleanField(default=True)
    deposit_customization = models.CharField(max_length=20, choices=DEPOSIT_CHOICES, default=DEPOSIT_DEFAULT)
    priority_marketplace_ranking = models.BooleanField(default=False)
    advanced_calendar_tools = models.BooleanField(default=False)
    auto_followups = models.BooleanField(default=False)
    ai_assistant = models.CharField(max_length=20, choices=AI_CHOICES, default=AI_ADDON)
    performance_analytics = models.CharField(max_length=20, choices=PERF_CHOICES, default=PERF_NONE)
    ghost_client_reengagement = models.BooleanField(default=False)

    def __str__(self):
        return self.name

class ShopSubscription(models.Model):
    """
    Links a Shop to a SubscriptionPlan, tracking its current status and validity period.
    """
    STATUS_ACTIVE = "active"
    STATUS_EXPIRED = "expired"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    shop = models.OneToOneField("api.Shop", on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, related_name="shops")
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    stripe_subscription_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    
    def __str__(self):
        plan_name = self.plan.name if self.plan else "—"
        return f"{self.shop.name} - {plan_name} ({self.status})"

    @property
    def is_active(self):
        return self.status == self.STATUS_ACTIVE and self.end_date > timezone.now()

# Signal to create a default (Foundation) subscription for a new shop
@receiver(post_save, sender='api.Shop')
def create_default_subscription_for_new_shop(sender, instance, created, **kwargs):
    if created:
        foundation_plan, _ = SubscriptionPlan.objects.get_or_create(
            name=SubscriptionPlan.FOUNDATION,
            defaults={
                'monthly_price': 0,
                'commission_rate': 10.00,
                'marketplace_profile': True,
                'instant_booking_payments': True,
                'automated_reminders': True,
                'smart_rebooking_prompts': True,
                'deposit_customization': SubscriptionPlan.DEPOSIT_DEFAULT,
                'priority_marketplace_ranking': False,
                'advanced_calendar_tools': False,
                'auto_followups': False,
                'ai_assistant': SubscriptionPlan.AI_ADDON,
                'performance_analytics': SubscriptionPlan.PERF_NONE,
                'ghost_client_reengagement': False,
            }
        )
        
        ShopSubscription.objects.create(
            shop=instance,
            plan=foundation_plan,
            start_date=timezone.now(),
            end_date=timezone.now() + relativedelta(years=100), # Long duration for free plan
            status=ShopSubscription.STATUS_ACTIVE
        )

        instance.apply_plan_defaults(overwrite=False)
@receiver(post_save, sender=ShopSubscription)
def apply_defaults_on_subscription_change(sender, instance, created, **kwargs):
    """
    When a shop gets/updates a subscription, apply the correct defaults.
    We don't overwrite user-changed values; we only fill empties by default.
    """
    if instance.shop:
        instance.shop.apply_plan_defaults(overwrite=False)