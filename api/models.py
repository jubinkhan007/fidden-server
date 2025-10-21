# api/models.py

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.conf import settings
from datetime import timedelta

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.db.models import Q
import uuid
from subscriptions.models import SubscriptionPlan,ShopSubscription
from django.db import transaction
# from payments.models import Booking
import logging
logger = logging.getLogger(__name__)

class Shop(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("rejected", "Rejected"),
        ("verified", "Verified"),
    ]

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='shop'
    )
    name = models.CharField(max_length=255)
    address = models.TextField()
    location = models.CharField(max_length=255, blank=True, null=True)
    capacity = models.PositiveIntegerField()
    start_at = models.TimeField()
    close_at = models.TimeField()
    # NEW: per-day overrides; keys: mon,tue,wed,thu,fri,sat,sun
    # value: list of [start, end] strings in "HH:MM" 24h format, e.g.
    # {"mon":[["09:00","14:00"],["15:00","18:00"]],"thu":[["13:00","17:00"]]}
    business_hours = models.JSONField(default=dict, blank=True)
    # 🆕 Break time fields
    break_start_time = models.TimeField(blank=True, null=True)
    break_end_time = models.TimeField(blank=True, null=True)
    about_us = models.TextField(blank=True, null=True)
    shop_img = models.ImageField(upload_to='shop/', blank=True, null=True)
    ai_partner_name = models.CharField(max_length=50, blank=True, null=True, default="Amara")

    close_days = models.JSONField(
        default=list,
        blank=True,
        help_text="List of closed days (e.g., ['monday', 'tuesday'])"
    )

    #default value for all the shops
    default_is_deposit_required = models.BooleanField(
        default=True,
        help_text="Default setting for whether deposits are required for new services"
    )

    default_deposit_type = models.CharField(
        max_length=10,
        choices=[('fixed', 'Fixed Amount'), ('percentage', 'Percentage')],
        default='percentage',
        null=True,
        blank=True,
        help_text="Default deposit type for new services"
    )

    default_deposit_percentage = models.PositiveIntegerField(
        default=20,
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Default percentage deposit for new services"
    )

    #  new field
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="pending"
    )
    free_cancellation_hours = models.PositiveIntegerField(default=24)
    cancellation_fee_percentage = models.PositiveIntegerField(default=50)
    no_refund_hours = models.PositiveIntegerField(default=4)


    is_deposit_required = models.BooleanField(default=False, help_text="Is a deposit required for booking?")
    # deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="The fixed amount for the deposit.")

    is_verified = models.BooleanField(default=False)  # renamed (typo fix)

    @property
    def ranking_power(self):
        if hasattr(self, 'subscription') and self.subscription.is_active:
            return self.subscription.plan.ranking_power
        return 0

    @property
    def subscription_features(self):
        """
        Returns a dictionary of feature flags for the shop's current plan.
        Returns default (most restrictive) values if no active subscription.
        """
        if hasattr(self, 'subscription') and self.subscription.is_active:
            plan = self.subscription.plan
            return {
                'deposit_customization': plan.deposit_customization,
                'priority_marketplace_ranking': plan.priority_marketplace_ranking,
                'advanced_calendar_tools': plan.advanced_calendar_tools,
                'auto_followups': plan.auto_followups,
                'ai_assistant': plan.ai_assistant,
                'performance_analytics': plan.performance_analytics,
                'ghost_client_reengagement': plan.ghost_client_reengagement,
            }
        # Default features for inactive/no subscription
        return {
            'deposit_customization': 'default',
            'priority_marketplace_ranking': False,
            'advanced_calendar_tools': False,
            'auto_followups': False,
            'ai_assistant': 'addon',
            'performance_analytics': 'none',
            'ghost_client_reengagement': False,
        }

    ##update all service new method
    def update_all_service_deposits(self):
        """Update all services' deposit amounts based on shop's default percentage"""
        if self.default_deposit_type == 'percentage' and self.default_deposit_percentage:
            self.services.filter(deposit_type='percentage').update(
                deposit_percentage=self.default_deposit_percentage
            )
            # Calculate deposit_amount for each service
            for service in self.services.all():
                service.deposit_type = 'percentage'
                service.deposit_percentage = self.default_deposit_percentage
                base_price = service.discount_price if service.discount_price and service.discount_price > 0 else service.price
                if base_price:
                    service.deposit_amount = (base_price * self.default_deposit_percentage) / 100
                    service.save(update_fields=['deposit_amount'])

    ## New method toa add default value to the shop but subscription based
    def apply_plan_defaults(self, overwrite=False):
        """
        Apply plan-based defaults from GlobalSettings to this shop.

        overwrite=False will only fill values if they are empty/zero.
        """
        from .models import GlobalSettings  # local import to avoid circulars
        settings = GlobalSettings.get_settings()

        plan = None
        if hasattr(self, 'subscription') and self.subscription and self.subscription.plan:
            plan = self.subscription.plan.name

        # Defaults from GlobalSettings
        dep_required = settings.default_deposit_required
        dep_type = settings.default_deposit_type
        dep_pct = settings.default_deposit_percentage
        # dep_amount = settings.default_deposit_amount

        free_cancel = settings.default_free_cancellation_hours
        cancel_fee = settings.default_cancellation_fee_percentage
        no_refund = settings.default_no_refund_hours

        def set_field(field_name, value):
            current = getattr(self, field_name, None)
            if overwrite:
                setattr(self, field_name, value)
            else:
                # Only apply if empty/zero/None
                if current in (None, 0, 0.0, '') or (isinstance(current, bool) and current is False):
                    setattr(self, field_name, value)

        if plan == 'Foundation':
            # Apply all defaults
            set_field('is_deposit_required', dep_required)
            set_field('default_deposit_type', dep_type)
            set_field('default_deposit_percentage', dep_pct)
            set_field('free_cancellation_hours', free_cancel)
            set_field('cancellation_fee_percentage', cancel_fee)
            set_field('no_refund_hours', no_refund)
        elif plan == 'Momentum':
            set_field('is_deposit_required', dep_required)
            set_field('default_deposit_type', dep_type)
            set_field('free_cancellation_hours', free_cancel)
            set_field('cancellation_fee_percentage', cancel_fee)
            set_field('no_refund_hours', no_refund)



        self.save(update_fields=[
            'is_deposit_required',
            'default_deposit_type',
            'default_deposit_percentage',
            'free_cancellation_hours',
            'cancellation_fee_percentage',
            'no_refund_hours',
        ])
        # NEW: Update all services after shop settings change
        self.update_all_service_deposits()

    def save(self, *args, **kwargs):
        print(f"Shop save() called for {self.name}")
        old_percentage = None
        if self.pk:  # Existing shop
            old_shop = Shop.objects.get(pk=self.pk)
            old_percentage = old_shop.default_deposit_percentage
            print(f"Old percentage: {old_percentage}, New percentage: {self.default_deposit_percentage}")

        # Auto-update is_verified based on status
        if self.status == "verified":
            self.is_verified = True
        else:
            self.is_verified = False
        super().save(*args, **kwargs)

        # Update services if deposit percentage changed
        if old_percentage != self.default_deposit_percentage:
            print(f"Percentage changed! Updating services...")
            self.update_all_service_deposits()
        else:
            print("No percentage change detected")
    
    # helper (not required but handy)
    def get_intervals_for_date(self, date_obj):
        """Return a list of (start_time, end_time) for a given date.
        Uses per-day overrides if present, else falls back to start_at/close_at.
        """
        import datetime as _dt
        day_key = date_obj.strftime("%a").lower()[:3]  # 'Mon'->'mon'
        overrides = (self.business_hours or {}).get(day_key, [])
        if overrides:
            out = []
            for pair in overrides:
                try:
                    s, e = pair
                    sh, sm = map(int, s.split(":"))
                    eh, em = map(int, e.split(":"))
                    out.append((_dt.time(sh, sm), _dt.time(eh, em)))
                except Exception:
                    continue
            return out
        # default single interval
        return [(self.start_at, self.close_at)]

    def __str__(self):
        return self.name

class VerificationFile(models.Model):
    shop = models.ForeignKey(
        "Shop",
        on_delete=models.CASCADE,
        related_name="verification_files"
    )
    file = models.FileField(
        upload_to="shop/verifications/",
        help_text="Upload verification document (e.g., trade license, ID card)"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.shop.name} - {self.file.name}"

class ServiceCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    sc_img = models.ImageField(upload_to='services-category/', blank=True, null=True)

    def __str__(self):
        return self.name

class Service(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='services')
    category = models.ForeignKey(ServiceCategory, on_delete=models.CASCADE, related_name='services')
    title = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True,  default=0)
    description = models.TextField(blank=True, null=True)
    service_img = models.ImageField(upload_to='services/', blank=True, null=True)
    requires_age_18_plus = models.BooleanField(default=False)

    ## adding new field for experimental
    # Deposit settings
    is_deposit_required = models.BooleanField(default=False)
    deposit_type = models.CharField(
        max_length=10,
        choices=[('fixed', 'Fixed Amount'), ('percentage', 'Percentage')],
        null=True,
        blank=True
    )
    deposit_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Fixed deposit amount (if deposit_type is 'fixed')"
    )
    deposit_percentage = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Percentage deposit (if deposit_type is 'percentage')"
    )
    duration = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Duration of the service in minutes"
    )
    capacity = models.PositiveIntegerField(
        default=1,
        help_text="Maximum number of people who can take this service at a time"
    )
    is_active = models.BooleanField(default=True)

    ##new calculation method
    def calculate_deposit_amount(self):
        """Calculate deposit amount based on percentage and service price"""
        if self.deposit_type == 'percentage' and self.deposit_percentage:
            # Use discount_price if it exists and > 0, otherwise use price
            base_price = self.discount_price if self.discount_price and self.discount_price > 0 else self.price
            if base_price:
                self.deposit_amount = (base_price * self.deposit_percentage) / 100
        elif self.deposit_type == 'fixed':
            # Keep existing deposit_amount for fixed type
            pass

    ##new method
    def save(self, *args, **kwargs):
        self.calculate_deposit_amount()
        is_new = self.pk is None
        if is_new and self.shop:
            # apply service-level defaults on create based on shop plan
            from .models import GlobalSettings
            settings = GlobalSettings.get_settings()

            plan = None
            if hasattr(self.shop, 'subscription') and self.shop.subscription and self.shop.subscription.plan:
                plan = self.shop.subscription.plan.name

            if plan == 'Foundation':
                if self.is_deposit_required is False:
                    self.is_deposit_required = settings.default_deposit_required
                if not self.deposit_type:
                    self.deposit_type = settings.default_deposit_type
                if self.deposit_type == 'percentage' and (not self.deposit_percentage):
                    self.deposit_percentage = settings.default_deposit_percentage
                # if self.deposit_type == 'fixed' and (not self.deposit_amount):
                #     self.deposit_amount = settings.default_deposit_amount

            elif plan == 'Momentum':
                # only deposit amount default
                if not self.deposit_type:
                    self.deposit_type = 'percentage'
                if self.deposit_type == 'percentage' and (not self.deposit_percentage):
                    self.deposit_percentage = settings.default_deposit_percentage
            # Icon: do nothing

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} ({self.shop.name})"

class RatingReview(models.Model):
    shop = models.ForeignKey(
        "Shop",
        on_delete=models.CASCADE,
        related_name="ratings"
    )
    service = models.ForeignKey(
        "Service",
        on_delete=models.CASCADE,
        related_name="ratings"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ratings"
    )
    booking = models.OneToOneField(
        "payments.Booking",   #  each booking can have only one review
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="review"
    )
    rating = models.PositiveSmallIntegerField(
        choices=[(1, "1 Star"), (2, "2 Stars"), (3, "3 Stars"), (4, "4 Stars"), (5, "5 Stars")],
        help_text="Rating from 1 to 5"
    )
    review = models.TextField(blank=True, null=True)
    review_img = models.ImageField(upload_to="reviews/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        if self.user:
            user_name = self.user.name or "Anonymous"
        else:
            user_name = "Anonymous"
        return f"{user_name} - {self.rating}⭐ for {self.service.title}"

    # Convenience method to get all replies for this review
    def get_replies(self):
        return self.replies.all()

    # Property to check if the review has any replies
    @property
    def has_replies(self):
        return self.replies.exists()

class Reply(models.Model):
    rating_review = models.ForeignKey(
        RatingReview,
        on_delete=models.CASCADE,
        related_name="replies"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="review_replies"
    )
    message = models.TextField(
        help_text="Reply message to the review"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Replies"
        ordering = ["created_at"]  # Show oldest first for conversation flow

    def __str__(self):
        if self.user:
            user_name = self.user.name or "Anonymous"
        else:
            user_name = "Anonymous"
        return f"Reply by {user_name} to review #{self.rating_review.id}"

class Slot(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='slots')
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='slots')
    start_time = models.DateTimeField(db_index=True)
    end_time = models.DateTimeField()
    capacity_left = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['service', 'start_time'], name='uniq_service_slot_start')
        ]
        ordering = ['start_time']
        indexes = [
            models.Index(fields=['shop', 'start_time']),
        ]

    def save(self, *args, **kwargs):
        if not self.end_time:
            self.end_time = self.start_time + timedelta(minutes=self.service.duration or 30)
        if self.capacity_left is None:
            self.capacity_left = self.service.capacity or 1
        super().save(*args, **kwargs)

    def __str__(self):
        # Avoid self.shop.name / self.service.title (relation hits)
        try:
            dt = timezone.localtime(self.start_time)
        except Exception:
            dt = self.start_time
        return f"Slot #{self.pk} @ {dt:%Y-%m-%d %H:%M}"

class SlotBooking(models.Model):
    STATUS_CHOICES = [
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled')
    ]
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('refund', 'Refund'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='slot_bookings')
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='slot_bookings')
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='slot_bookings')
    slot = models.ForeignKey(Slot, on_delete=models.CASCADE, related_name='bookings')
    start_time = models.DateTimeField(db_index=True)
    end_time = models.DateTimeField()
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='confirmed')
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_time']
        indexes = [
            models.Index(fields=['shop', 'start_time', 'end_time']),
            models.Index(fields=['service', 'start_time']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'slot'],
                condition=Q(status='confirmed'),
                name='uniq_user_slot_confirmed'
            )
        ]

    def __str__(self):
        # Avoid self.user / self.service.title / self.shop.name
        try:
            dt = timezone.localtime(self.start_time)
        except Exception:
            dt = self.start_time
        return f"Booking #{self.pk} @ {dt:%Y-%m-%d %H:%M}"


# NEW: only time-of-day per service to disable across ALL dates
class ServiceDisabledTime(models.Model):
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="disabled_times"
    )
    start_time = models.TimeField(db_index=True)  # time-of-day

    class Meta:
        unique_together = ('service', 'start_time')
        ordering = ['start_time']

    def __str__(self):
        return f"{self.service.title} @ {self.start_time}"

class FavoriteShop(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='favorite_shops'
    )
    shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        related_name='favorited_by'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'shop')  # Prevent the same shop from being favorited multiple times by the same user
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} ❤️ {self.shop.name}"

class Promotion(models.Model):
    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=500, blank=True, null=True)
    amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Discount amount or promotion value"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.amount}"

class ServiceWishlist(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='service_wishlist'
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name='wishlisted_by'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'service')  # Prevent duplicate wishlist entries
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} ⭐ {self.service.title}"

class ChatThread(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="threads")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="threads")
    created_at = models.DateTimeField(auto_now_add=True)

class Message(models.Model):
    thread = models.ForeignKey(ChatThread, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField()
    is_read = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)

class Device(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="devices", on_delete=models.CASCADE)
    fcm_token = models.CharField(max_length=255)
    device_token = models.CharField(max_length=255)
    device_type = models.CharField(max_length=50, default="android")  # android/ios
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class Notification(models.Model):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    message = models.CharField(max_length=512)
    notification_type = models.CharField(max_length=50, default="chat")
    data = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

class Revenue(models.Model):
    shop = models.ForeignKey(
        "Shop",
        on_delete=models.CASCADE,
        related_name="revenues"
    )
    revenue = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Total revenue amount"
    )
    timestamp = models.DateField(  # Changed from DateTimeField
        auto_now_add=True,
        help_text="Revenue record date"
    )

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Revenue"
        verbose_name_plural = "Revenues"

    def __str__(self):
        return f"{self.shop.name} – {self.revenue} at {self.timestamp:%Y-%m-%d}"

class Coupon(models.Model):
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, null=True)
    amount = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True,
        help_text="Discount value. Flat or percentage depending on in_percentage"
    )
    in_percentage = models.BooleanField(
        default=False,
        help_text="If True, discount is percentage-based"
    )
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='shop_coupons')
    services = models.ManyToManyField(Service, related_name='service_coupons')  # <-- Multiple services
    validity_date = models.DateField()
    is_active = models.BooleanField(default=True)
    max_usage_per_user = models.PositiveIntegerField(
        blank=True, null=True,
        help_text="Max times a user can use this coupon"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.code

    @property
    def discount_type(self):
        return 'percentage' if self.in_percentage else 'amount'

    def save(self, *args, **kwargs):
        # Auto-generate code if empty
        if not self.code:
            shop_initial = self.shop.name[0].upper() if self.shop and self.shop.name else "S"
            service_initial = ""
            # If multiple services exist, take first service's title initial
            if self.pk:  # When updating, services already linked
                first_service = self.services.first()
                service_initial = first_service.title[0].upper() if first_service else "X"
            else:
                service_initial = "X"  # Temporary placeholder for new object
            self.code = f"{shop_initial}{service_initial}{int(timezone.now().timestamp())}"
        # Auto-disable expired coupon
        if self.validity_date < timezone.now().date():
            self.is_active = False
        super().save(*args, **kwargs)


## new global settings model
class GlobalSettings(models.Model):
    """
    Global default settings that apply to all shops regardless of subscription plan.
    Admin can change these values to affect all shops.
    """
    # Deposit defaults
    default_deposit_required = models.BooleanField(
        default=True,
        help_text="Default: Is deposit required for all shops?"
    )
    default_deposit_type = models.CharField(
        max_length=10,
        choices=[('fixed', 'Fixed Amount'), ('percentage', 'Percentage')],
        default='percentage',
        help_text="Default deposit type for all shops"
    )
    default_deposit_percentage = models.PositiveIntegerField(
        default=20,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Default percentage deposit (e.g., 20 means 20%)"
    )
    

    # Cancellation policy defaults
    default_free_cancellation_hours = models.PositiveIntegerField(
        default=24,
        help_text="Default hours before booking for free cancellation"
    )
    default_cancellation_fee_percentage = models.PositiveIntegerField(
        default=50,
        help_text="Default cancellation fee percentage"
    )
    default_no_refund_hours = models.PositiveIntegerField(
        default=4,
        help_text="Default hours before booking when no refund is given"
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Global Settings"
        verbose_name_plural = "Global Settings"

    def __str__(self):
        return f"Global Settings (Updated: {self.updated_at})"

    @classmethod
    def get_settings(cls):
        settings, _ = cls.objects.get_or_create(pk=1)
        return settings


# Update the GlobalSettings signal
@receiver(post_save, sender=GlobalSettings)
def update_foundation_shops_on_settings_change(sender, instance, **kwargs):
    foundation_shops = Shop.objects.filter(
        subscription__plan__name=SubscriptionPlan.FOUNDATION,
        subscription__status=ShopSubscription.STATUS_ACTIVE
    )

    for shop in foundation_shops:
        shop.apply_plan_defaults(overwrite=True)
        # This will now also update all services via update_all_service_deposits()

class PerformanceAnalytics(models.Model):
    shop = models.OneToOneField(Shop, on_delete=models.CASCADE, related_name='analytics')
    total_revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_bookings = models.PositiveIntegerField(default=0)
    cancellation_rate = models.FloatField(default=0.0)
    repeat_customer_rate = models.FloatField(default=0.0)
    average_rating = models.FloatField(default=0.0)
    top_service = models.CharField(max_length=255, blank=True, null=True)
    peak_booking_time = models.CharField(max_length=255, blank=True, null=True)
    customer_demographics = models.JSONField(default=dict)
    no_shows_filled = models.PositiveIntegerField(default=0)
    week_start_date = models.DateField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Analytics for {self.shop.name}"
    

class AIAutoFillSettings(models.Model):
    """ Provider-specific settings for the No-Show Auto-Fill feature. """
    shop = models.OneToOneField(Shop, on_delete=models.CASCADE, related_name='ai_settings')
    is_active = models.BooleanField(default=False)
    no_show_window_minutes = models.PositiveIntegerField(default=10, help_text="Minutes after start time to mark as no-show.")
    auto_fill_scope_hours = models.PositiveIntegerField(default=48, help_text="How many hours into the future to look for candidates.")
    # TODO: Add other settings like incentives, quiet hours, etc., as fields here.
    
    def __str__(self):
        return f"AI Settings for {self.shop.name}"

class WaitlistEntry(models.Model):
    """ A user waiting for a specific service or any opening at a shop. """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='waitlist_entries')
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='waitlist')
    service = models.ForeignKey(Service, on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    opted_in_offers = models.BooleanField(default=True, help_text="User agrees to receive short-notice offers.")
    
    class Meta:
        unique_together = ('user', 'shop', 'service')

    def __str__(self):
        return f"{self.user.email} on waitlist for {self.shop.name}"

class AutoFillLog(models.Model):
    """ Audit log for tracking auto-fill events. """
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='autofill_logs')
    original_booking = models.ForeignKey('payments.Booking', on_delete=models.SET_NULL, null=True, related_name='autofill_trigger')
    offered_slot = models.OneToOneField('Slot', on_delete=models.SET_NULL, null=True, blank=True, related_name='autofill_log')
    filled_by_booking = models.ForeignKey('payments.Booking', on_delete=models.SET_NULL, null=True, related_name='autofill_success')
    status = models.CharField(max_length=30, default='initiated')
    revenue_recovered = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Auto-fill log for {self.shop.name} at {self.created_at}"
# --- DJANGO SIGNAL TO TRIGGER AUTO-FILL ---

# api/models.py
@receiver(post_save, dispatch_uid="api_on_booking_status_change")
def on_booking_status_change(sender, instance, **kwargs):
    # only react to models that actually have a status
    if not hasattr(instance, "status"):
        return

    if instance.status in ("no-show", "late-cancel"):
        # 1) immediately cancel the slot-level record (prevents overlap)
        try:
            sb = instance.slot  # api.SlotBooking
            if sb and sb.status != "cancelled":
                sb.status = "cancelled"
                sb.save(update_fields=["status"])
        except Exception:
            pass

        # 2) kick off outreach after the transaction commits
        from api.tasks import trigger_no_show_auto_fill
        transaction.on_commit(lambda: trigger_no_show_auto_fill.delay(instance.id))
