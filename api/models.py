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
    # V1 Fix: Added 'unverified' for scalable onboarding
    # Shops can operate immediately, no manual approval bottleneck
    STATUS_CHOICES = [
        ("unverified", "Unverified"),  # Can operate, not yet reviewed
        ("pending", "Pending"),         # Awaiting admin review
        ("rejected", "Rejected"),       # Failed verification
        ("verified", "Verified"),       # Fully approved
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
    # 🆕 Shop's local timezone for slot generation (IANA format, e.g. "America/New_York")
    time_zone = models.CharField(
        max_length=50, 
        default="America/New_York",
        help_text="IANA timezone (e.g., 'America/New_York', 'America/Los_Angeles')"
    )
    
    # 🆕 Social Links
    instagram_url = models.URLField(max_length=200, blank=True, null=True)
    tiktok_url = models.URLField(max_length=200, blank=True, null=True)
    youtube_url = models.URLField(max_length=200, blank=True, null=True)
    website_url = models.URLField(max_length=200, blank=True, null=True)

    # Missing field restored to match DB schema
    niche = models.CharField(max_length=50, default='Barber', blank=True, null=True)

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

    # V1 Fix: Default to 'unverified' so shops can operate immediately
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="unverified"
    )
    free_cancellation_hours = models.PositiveIntegerField(default=24)
    cancellation_fee_percentage = models.PositiveIntegerField(default=50)
    no_refund_hours = models.PositiveIntegerField(default=4)

    # ---------------------------
    # RULE-BASED SCHEDULING FIELDS
    # ---------------------------
    default_interval_minutes = models.PositiveIntegerField(
        default=15,
        choices=[(5, '5 min'), (10, '10 min'), (15, '15 min'), (30, '30 min'), (60, '60 min')],
        help_text="Default slot interval for time selection grid"
    )

    access_hours = models.JSONField(
        default=dict, blank=True,
        help_text="Optional access hours that constrain all providers"
    )

    default_availability_ruleset = models.ForeignKey(
        'AvailabilityRuleSet',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='default_for_shops'
    )
    
    # Feature flag for gradual rollout
    use_rule_based_availability = models.BooleanField(
        default=False,
        help_text="Enable new rule-based availability engine for this shop"
    )

    def apply_plan_defaults(self, overwrite=False):
        """
        Placeholder for subscriptions app integration.
        Populates shop settings based on the subscription plan.
        """
        pass

# ------------------------------------




    is_deposit_required = models.BooleanField(default=False, help_text="Is a deposit required for booking?")
    # deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="The fixed amount for the deposit.")

    is_verified = models.BooleanField(default=False)  # renamed (typo fix)
    
    # V1 Fix: Notification cadence tracking (prevents over-triggering)
    last_weekly_wrap_sent_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When weekly wrap-up notification was last sent (stored in UTC)"
    )
    last_week_ahead_sent_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When week-ahead forecast was last sent (stored in UTC)"
    )
    last_daily_snapshot_sent_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When daily snapshot was last sent (stored in UTC)"
    )

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
            
            # --- Get Old State ---
            old_percentage = None
            orig_status = None
            send_verification_notification = False

            if self.pk:  # Existing shop
                try:
                    # Get the original state from the database
                    orig_shop = Shop.objects.get(pk=self.pk)
                    old_percentage = orig_shop.default_deposit_percentage
                    orig_status = orig_shop.status
                    print(f"Old status: {orig_status}, New status: {self.status}")
                    print(f"Old percentage: {old_percentage}, New percentage: {self.default_deposit_percentage}")
                    
                    # Check if the status is changing from 'pending' to 'verified'
                    if orig_status == 'pending' and self.status == 'verified':
                        send_verification_notification = True
                        
                except Shop.DoesNotExist:
                    pass # This is a new shop

            # --- Logic to run *before* save ---
            
            # Auto-update is_verified based on status
            if self.status == "verified":
                self.is_verified = True
            else:
                self.is_verified = False

            # --- Call the original save method ---
            super().save(*args, **kwargs)

            # --- Logic to run *after* save ---

            # 1. Update services if deposit percentage changed
            if old_percentage != self.default_deposit_percentage:
                print(f"Percentage changed! Updating services...")
                self.update_all_service_deposits()
            else:
                print("No percentage change detected")

            # 2. Send notification if verification just happened
            if send_verification_notification and self.owner:
                try:
                    from .utils.fcm import notify_user
                    logger.info(f"Shop {self.id} verified, sending notification to owner {self.owner.id}")
                    
                    notify_user(
                        user=self.owner,
                        message="Congratulations! Your shop has been verified.", # This is the short message
                        notification_type="shop_verified", # For a deep link handler
                        data={
                            "title": "Your Shop is Live! ✨",
                            "summary": f"Congratulations! Your shop '{self.name}' has been verified by our team and is now live.",
                            "deep_link": f"fidden://shop/{self.id}", # Example deep link
                            "shop_id": str(self.id)
                        }
                    )
                except Exception as e:
                    # Log the error but don't crash the save operation
                    logger.error(f"Failed to send verification push notification to owner {self.owner.id}: {e}", exc_info=True)
    
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

# ------------------------------------
# NEW RULE-BASED SCHEDULING MODELS
# ------------------------------------

class AvailabilityRuleSet(models.Model):
    """
    Weekly availability template with breaks.
    Can be assigned to a Provider or used as shop-level default.
    """
    name = models.CharField(max_length=100, blank=True)
    timezone = models.CharField(max_length=50, default='America/New_York')
    interval_minutes = models.PositiveIntegerField(
        default=15,
        choices=[(5, '5 min'), (10, '10 min'), (15, '15 min'), (30, '30 min'), (60, '60 min')]
    )
    
    # Weekly rules: {"mon": [["09:00", "12:00"], ["13:00", "18:00"]], ...}
    weekly_rules = models.JSONField(default=dict)
    
    # Breaks: [{"start": "12:00", "end": "13:00", "days": ["mon", "tue", "wed", "thu", "fri"]}]
    breaks = models.JSONField(default=list)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def clean(self):
        """Validate timezone is a valid IANA identifier."""
        from django.core.exceptions import ValidationError
        from zoneinfo import ZoneInfo
        
        try:
            ZoneInfo(self.timezone)
        except Exception:
            raise ValidationError({
                'timezone': f"'{self.timezone}' is not a valid IANA timezone identifier."
            })
    
    def __str__(self):
        return f"{self.name or 'Ruleset'} ({self.timezone})"


class Provider(models.Model):
    """
    Represents a bookable person (employee or independent contractor).
    For single-owner shops, the owner is the implicit provider.
    """
    PROVIDER_TYPE_CHOICES = [
        ('employee', 'Employee'),           # Shifts managed by business
        ('independent', 'Independent'),     # Self-managed schedule
    ]
    
    shop = models.ForeignKey('Shop', on_delete=models.CASCADE, related_name='providers')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, 
                            related_name='provider_profiles', null=True, blank=True)
    name = models.CharField(max_length=255)
    provider_type = models.CharField(max_length=15, choices=PROVIDER_TYPE_CHOICES, default='employee')
    is_active = models.BooleanField(default=True)
    profile_image = models.ImageField(upload_to='providers/', blank=True, null=True)
    
    # Services this provider can perform
    services = models.ManyToManyField('Service', related_name='providers', blank=True)
    
    # Opt-in for "Any Provider" aggregated view
    allow_any_provider_booking = models.BooleanField(default=True)
    
    # Availability ruleset link
    availability_ruleset = models.ForeignKey(
        'AvailabilityRuleSet', 
        on_delete=models.SET_NULL, 
        null=True, blank=True,
        related_name='providers'
    )
    
    # Processing overlap concurrency limit
    max_concurrent_processing_jobs = models.PositiveIntegerField(
        default=1,
        help_text="Maximum number of processing-phase services this provider can handle simultaneously"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} ({self.shop.name})"


class ProviderDayLock(models.Model):
    """
    Used for pessimistic locking during booking creation.
    Can lock a specific provider on a date, or the whole shop on a date.
    """
    shop = models.ForeignKey('Shop', on_delete=models.CASCADE, related_name='day_locks', null=True, blank=True)
    provider = models.ForeignKey('Provider', on_delete=models.CASCADE, related_name='day_locks', null=True, blank=True)
    date = models.DateField(db_index=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['shop', 'provider', 'date'], 
                name='uniq_shop_provider_date_lock'
            )
        ]
        
    def __str__(self):
        return f"Lock: {self.shop.name} | {self.provider.name if self.provider else 'ALL'} | {self.date}"


class AvailabilityException(models.Model):
    """
    Date-specific override for a provider's schedule.
    """
    provider = models.ForeignKey('Provider', on_delete=models.CASCADE, related_name='exceptions')
    date = models.DateField(db_index=True)
    
    is_closed = models.BooleanField(default=False)
    override_rules = models.JSONField(default=list, blank=True)
    override_breaks = models.JSONField(default=list, blank=True)
    note = models.CharField(max_length=255, blank=True)
    
    class Meta:
        unique_together = ['provider', 'date']


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


class GalleryItem(models.Model):
    """
    Client-facing gallery for service providers to showcase their work.
    Auto-generates thumbnail on upload.
    """
    shop = models.ForeignKey(
        "Shop",
        on_delete=models.CASCADE,
        related_name="gallery_items"
    )
    image = models.ImageField(upload_to="gallery/")
    thumbnail = models.ImageField(upload_to="gallery/thumbnails/", blank=True, null=True)
    caption = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    service = models.ForeignKey(
        "Service",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gallery_items"
    )
    category_tag = models.CharField(max_length=50, blank=True, null=True)
    tags = models.JSONField(default=list, blank=True)
    is_public = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.shop.name} - {self.caption or 'Gallery Item'}"

    def save(self, *args, **kwargs):
        # Auto-generate thumbnail if image is provided and thumbnail is not
        if self.image and not self.thumbnail:
            self._generate_thumbnail()
        super().save(*args, **kwargs)

    def _generate_thumbnail(self, max_size=300):
        """Generate a thumbnail version of the image."""
        from PIL import Image
        from io import BytesIO
        from django.core.files.base import ContentFile
        import os

        try:
            img = Image.open(self.image)
            # Convert to RGB if necessary (for PNG transparency)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            
            thumb_io = BytesIO()
            img.save(thumb_io, format='JPEG', quality=85)
            
            # Generate thumbnail filename
            base_name = os.path.splitext(os.path.basename(self.image.name))[0]
            thumb_name = f"thumb_{base_name}.jpg"
            
            self.thumbnail.save(thumb_name, ContentFile(thumb_io.getvalue()), save=False)
        except Exception as e:
            logger.warning(f"Failed to generate thumbnail for gallery item: {e}")

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

    # ---------------------------
    # RULE-BASED SCHEDULING FIELDS
    # ---------------------------
    # Buffer fields
    buffer_before_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Buffer time required before this service (in minutes)"
    )

    buffer_after_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Buffer time required after this service (in minutes)"
    )

    # Processing overlap fields
    provider_block_minutes = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Minutes provider is actively occupied. Defaults to duration if not set."
    )

    allow_processing_overlap = models.BooleanField(
        default=False,
        help_text="If True, provider can start new bookings after provider_block_minutes"
    )

    @property
    def effective_provider_block_minutes(self):
        """Returns provider_block_minutes or duration if not set."""
        if self.provider_block_minutes is not None:
            return self.provider_block_minutes
        return self.duration or 0

    @property
    def total_duration_minutes(self):
        """Total time from buffer_before start to buffer_after end."""
        return (self.duration or 0) + self.buffer_before_minutes + self.buffer_after_minutes

    @property
    def provider_busy_minutes(self):
        """Time provider is actively occupied (busy interval length)."""
        return self.buffer_before_minutes + self.effective_provider_block_minutes

    @property
    def processing_window_minutes(self):
        """Duration of processing phase (provider free but service ongoing)."""
        return max(0, (self.duration or 0) - self.effective_provider_block_minutes)

    def clean(self):
        """Validation: provider_block_minutes must not exceed duration."""
        super().clean()
        from django.core.exceptions import ValidationError
        if self.provider_block_minutes is not None:
            if self.provider_block_minutes > (self.duration or 0):
                raise ValidationError({
                    'provider_block_minutes': 'Cannot exceed service duration'
                })

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
        ('pending', 'Pending'),      # Awaiting payment
        ('confirmed', 'Confirmed'),  # Payment received
        ('cancelled', 'Cancelled')   # Cancelled or payment failed
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
    provider = models.ForeignKey(
        'Provider', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='slot_bookings'
    )
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


class BookingAddOn(models.Model):
    """
    Represents an additional service added to a main booking.
    """
    booking = models.ForeignKey(
        SlotBooking, 
        on_delete=models.CASCADE, 
        related_name='add_ons'
    )
    service = models.ForeignKey(
        Service, 
        on_delete=models.CASCADE,
        related_name='addon_bookings'
    )
    price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Snapshot of the add-on price at the time of booking"
    )
    
    def save(self, *args, **kwargs):
        if not self.price:
            # Snapshot the price if not provided
            self.price = self.service.discount_price if (self.service.discount_price and self.service.discount_price > 0) else self.service.price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Add-on: {self.service.title} for Booking #{self.booking.id}"


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
    



# api/models.py (add this)

import uuid
from django.conf import settings
from django.db import models

class WeeklySummary(models.Model):
    """
    One row per shop per generated weekly recap.
    This powers the 'Your Week at a Glance' screen and Klaviyo/email content.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    shop = models.ForeignKey(
        'api.Shop',
        related_name='weekly_summaries',
        on_delete=models.CASCADE,
    )
    provider = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='weekly_summaries',
        on_delete=models.CASCADE,
    )

    # Week window that this summary covers
    week_start_date = models.DateField()
    week_end_date = models.DateField()

    # Core performance metrics
    total_appointments = models.PositiveIntegerField(default=0)
    revenue_generated = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # V1 Fix: Revenue breakdown for data credibility
    revenue_deposits = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Total deposits collected this week"
    )
    revenue_checkout = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Total checkout payments (remaining + tips) this week"
    )
    revenue_tips = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Total tips collected this week"
    )
    
    rebooking_rate = models.FloatField(default=0.0)         # percent (0-100)
    growth_rate = models.FloatField(default=0.0)            # WoW % revenue delta
    no_shows_filled = models.PositiveIntegerField(default=0)
    top_service = models.CharField(max_length=255, blank=True)
    top_service_count = models.PositiveIntegerField(default=0)
    open_slots_next_week = models.PositiveIntegerField(default=0)

    # Forecast helpers (e.g. "Estimated revenue: $2,850")
    forecast_estimated_revenue = models.DecimalField(
        max_digits=10, decimal_places=2, default=0
    )

    # AI / coaching layer
    ai_motivation = models.TextField(blank=True)  # "You didn't just style hair..."
    # Two action cards + any CTA context we want to show in-app
    ai_recommendations = models.JSONField(default=dict, blank=True)
    # Example structure:
    # {
    #   "revenue_booster": {
    #        "text": "...",
    #        "cta_label": "Yes, Create It",
    #        "cta_action": "generate_marketing_caption"
    #   },
    #   "retention_play": {
    #        "text": "...",
    #        "cta_label": "Send via SMS",
    #        "cta_action": "send_loyalty_sms"
    #   }
    # }

    delivered_channels = models.JSONField(default=list, blank=True)
    # e.g. ["push", "in_app", "email"]

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-week_end_date", "-created_at"]

    def __str__(self):
        return f"WeeklySummary<{self.shop_id} {self.week_start_date}→{self.week_end_date}>"




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
                
                # Restore capacity so it can be rebooked
                if sb.slot:
                    sb.slot.capacity_left += 1
                    sb.slot.save(update_fields=["capacity_left"])
        except Exception:
            pass

        # 2) kick off outreach after the transaction commits
        from api.tasks import trigger_no_show_auto_fill
        transaction.on_commit(lambda: trigger_no_show_auto_fill.delay(instance.id))

