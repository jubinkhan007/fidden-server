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

    NICHE_CHOICES = [
        ('fitness_trainer', 'Fitness Trainer'),
        ('tattoo_artist', 'Tattoo Artist'),
        ('barber', 'Barber'),
        ('hairstylist', 'Hairstylist'),
        ('nail_tech', 'Nail Tech'),
        ('makeup_artist', 'Makeup Artist'),
        ('esthetician', 'Esthetician'),
        ('massage_therapist', 'Massage Therapist'),
        ('other', 'Other'),
    ]

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='shop'
    )
    name = models.CharField(max_length=255)
    niche = models.CharField(
        max_length=50, 
        choices=NICHE_CHOICES, 
        default='other',
        help_text="DEPRECATED: Use 'niches' field instead. Kept for backward compatibility."
    )
    niches = models.JSONField(
        default=list,
        blank=True,
        help_text="List of service niches offered by this shop (e.g., ['tattoo_artist', 'barber'])"
    )
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

    @property
    def primary_niche(self):
        """
        Returns the primary niche for backward compatibility.
        Returns the first niche from niches list, or falls back to niche field, or 'other'.
        """
        if self.niches and len(self.niches) > 0:
            return self.niches[0]
        return self.niche if self.niche else 'other'
    
    def auto_detect_niches(self):
        """
        Auto-detect niches based on service categories AND titles offered by this shop.
        Maps service categories and titles to niches.
        
        Returns:
            list: Detected niches sorted by frequency (most common first)
        """
        # Mapping of keywords to niches
        KEYWORD_TO_NICHE_MAP = {
            # Haircut/Barber services
            'haircut': 'barber',
            'hair cut': 'barber',
            'beard': 'barber',
            'shave': 'barber',
            'barber': 'barber',
            'fade': 'barber',
            'trim': 'barber',
            
            # Hair styling
            'hair': 'hairstylist',
            'hairstyle': 'hairstylist',
            'braid': 'hairstylist',
            'locs': 'hairstylist',
            'dread': 'hairstylist',
            'perm': 'hairstylist',
            'color': 'hairstylist',
            
            # Nail services
            'nails': 'nail_tech',
            'nail': 'nail_tech',
            'manicure': 'nail_tech',
            'pedicure': 'nail_tech',
            'gel': 'nail_tech',
            'acrylic': 'nail_tech',
            
            # Skin/Beauty services
            'skincare': 'esthetician',
            'facial': 'esthetician',
            'waxing': 'esthetician',
            'skin': 'esthetician',
            'esthetic': 'esthetician',
            
            # Massage services
            'massage': 'esthetician',
            'spa': 'esthetician',
            'therapy': 'esthetician',
            'relax': 'esthetician',
            
            # Makeup
            'makeup': 'makeup_artist',
            'cosmetic': 'makeup_artist',
            'glam': 'makeup_artist',
            
            # Tattoo/Piercing - ENHANCED
            'tattoo': 'tattoo_artist',
            'piercing': 'tattoo_artist',
            'ink': 'tattoo_artist',
            'body art': 'tattoo_artist',
            'permanent': 'tattoo_artist',
            
            # Fitness
            'fitness': 'fitness_trainer',
            'training': 'fitness_trainer',
            'gym': 'fitness_trainer',
            'yoga': 'fitness_trainer',
            'workout': 'fitness_trainer',
        }
        
        # Get all service categories for this shop
        from collections import Counter
        niche_counts = Counter()
        
        for service in self.services.select_related('category').all():
            # Check both category AND title (not exclusive)
            
            # Check category name
            if service.category:
                category_name = service.category.name.lower()
                for keyword, niche in KEYWORD_TO_NICHE_MAP.items():
                    if keyword in category_name:
                        niche_counts[niche] += 1
                        break  # Only match once per category
            
            # ALSO check service title
            service_title = service.title.lower()
            for keyword, niche in KEYWORD_TO_NICHE_MAP.items():
                if keyword in service_title:
                    niche_counts[niche] += 1
                    break # Only match once per title
        
        # Return niches sorted by frequency (most common first)
        detected_niches = [niche for niche, count in niche_counts.most_common()]
        
        # If no niches detected, return ['other']
        return detected_niches if detected_niches else ['other']
    
    def update_niches_from_services(self, save=True):
        """
        Update this shop's niches field based on auto-detection from services.
        
        Args:
            save (bool): Whether to save the shop after updating niches
            
        Returns:
            list: The updated niches list
        """
        detected = self.auto_detect_niches()
        self.niches = detected
        
        if save:
            self.save(update_fields=['niches'])
        
        return self.niches

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
    
    # MUA Face Charts support - link to client
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='gallery_items',
        help_text="Link to client for Face Charts"
    )
    look_type = models.CharField(max_length=20, blank=True, help_text="For MUA face charts: natural, glam, bridal, etc.")
    
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
    
    # Nail Tech specific fields
    NAIL_STYLE_CHOICES = [
        ('', 'Not Applicable'),
        ('acrylic', 'Acrylic'),
        ('gel', 'Gel'),
        ('dip', 'Dip Powder'),
        ('natural', 'Natural/Manicure'),
        ('pedicure', 'Pedicure'),
        ('nail_art', 'Nail Art'),
    ]
    NAIL_SHAPE_CHOICES = [
        ('', 'Not Applicable'),
        ('coffin', 'Coffin'),
        ('almond', 'Almond'),
        ('stiletto', 'Stiletto'),
        ('square', 'Square'),
        ('round', 'Round'),
        ('oval', 'Oval'),
        ('squoval', 'Squoval'),
    ]
    nail_style_type = models.CharField(max_length=20, choices=NAIL_STYLE_CHOICES, blank=True, default='')
    nail_shape = models.CharField(max_length=20, choices=NAIL_SHAPE_CHOICES, blank=True, default='')
    is_fill_in = models.BooleanField(default=False, help_text="True for fill-in, False for new set")
    
    # MUA (Makeup Artist) specific fields
    LOOK_TYPE_CHOICES = [
        ('', 'Not Applicable'),
        ('natural', 'Natural'),
        ('glam', 'Glam'),
        ('bridal', 'Bridal'),
        ('editorial', 'Editorial'),
        ('sfx', 'Special Effects'),
    ]
    look_type = models.CharField(max_length=20, choices=LOOK_TYPE_CHOICES, blank=True, default='')
    is_mobile_service = models.BooleanField(default=False, help_text="Can travel to client location")
    
    # Hairstylist/Loctician specific fields
    HAIR_SERVICE_TYPE_CHOICES = [
        ('', 'Not Applicable'),
        ('cut', 'Cut'),
        ('color', 'Color'),
        ('style', 'Style'),
        ('treatment', 'Treatment'),
        ('braids', 'Braids'),
        ('locs', 'Locs'),
        ('extensions', 'Extensions'),
        ('wash', 'Wash & Style'),
    ]
    hair_service_type = models.CharField(max_length=20, choices=HAIR_SERVICE_TYPE_CHOICES, blank=True, default='')
    includes_consultation = models.BooleanField(default=False, help_text="Service includes consultation")
    
    # Esthetician/Massage Therapist specific fields
    ESTHETICIAN_SERVICE_TYPE_CHOICES = [
        ('', 'Not Applicable'),
        ('facial', 'Facial'),
        ('massage', 'Massage'),
        ('body', 'Body Treatment'),
        ('wax', 'Waxing'),
        ('lash', 'Lash/Brow'),
        ('peel', 'Chemical Peel'),
        ('microderm', 'Microdermabrasion'),
        ('wrap', 'Body Wrap'),
        ('scrub', 'Body Scrub'),
    ]
    esthetician_service_type = models.CharField(max_length=20, choices=ESTHETICIAN_SERVICE_TYPE_CHOICES, blank=True, default='')
    requires_health_disclosure = models.BooleanField(default=False, help_text="Requires health disclosure form")

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


# ==========================================
# PHASE 2: TATTOO ARTIST FEATURES 🖋️
# ==========================================

class PortfolioItem(models.Model):
    """
    Dedicated model for the 'Portfolio Manager'.
    Allows tagging (e.g., 'Realism', 'Blackwork') and descriptions.
    """
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="portfolio_items")
    image = models.ImageField(upload_to="portfolio/")
    tags = models.JSONField(default=list, blank=True, help_text="List of tags e.g. ['Realism', 'Color']")
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Portfolio Item {self.id} - {self.shop.name}"

class DesignRequest(models.Model):
    """
    Allows clients to send ideas/sketches to the artist before or after booking.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('discussing', 'Discussing'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="design_requests")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="design_requests")
    booking = models.ForeignKey("payments.Booking", on_delete=models.SET_NULL, null=True, blank=True, related_name="design_requests")
    
    description = models.TextField(help_text="User's idea or description")
    placement = models.CharField(max_length=100, help_text="e.g., Left Arm")
    size_approx = models.CharField(max_length=100, help_text="e.g., 3x3 inches")
    
    # For multiple reference images, we might need a separate model, 
    # but for simplicity/MVP we can use a JSONField of URLs or a single file field.
    # Let's use a separate model for images to allow multiple uploads.
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Design Request by {self.user} for {self.shop.name}"

class DesignRequestImage(models.Model):
    """
    Reference images for a DesignRequest.
    """
    request = models.ForeignKey(DesignRequest, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="design_requests/")
    created_at = models.DateTimeField(auto_now_add=True)

class ConsentFormTemplate(models.Model):
    """
    Shops can create their own legal waivers.
    """
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="consent_templates")
    title = models.CharField(max_length=255, default="General Waiver")
    content = models.TextField(help_text="The legal text of the waiver")
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} - {self.shop.name}"

class SignedConsentForm(models.Model):
    """
    Record of a user signing a form.
    """
    template = models.ForeignKey(ConsentFormTemplate, on_delete=models.SET_NULL, null=True)
    booking = models.ForeignKey("payments.Booking", on_delete=models.CASCADE, related_name="signed_forms")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="signed_forms")
    
    signature_image = models.ImageField(upload_to="signatures/")
    signed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Signed Form by {self.user} for Booking {self.booking_id}"

class IDVerificationRequest(models.Model):
    """
    Explicit tracker for ID verification status.
    """
    STATUS_CHOICES = [
        ('pending_upload', 'Pending Upload'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="id_verifications")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="id_verifications")
    booking = models.ForeignKey("payments.Booking", on_delete=models.SET_NULL, null=True, blank=True, related_name="id_verifications")
    
    front_image = models.ImageField(upload_to="id_verification/", blank=True, null=True)
    back_image = models.ImageField(upload_to="id_verification/", blank=True, null=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending_upload')
    rejection_reason = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"ID Verification for {self.user.name} - {self.status}"


class Consultation(models.Model):
    """Pre-tattoo consultation appointments"""
    
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('confirmed', 'Confirmed'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('no_show', 'No Show'),
    ]
    
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='consultations')
    customer_name = models.CharField(max_length=200)
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=20, blank=True)
    date = models.DateField()
    time = models.TimeField()
    duration_minutes = models.IntegerField(default=30)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    notes = models.TextField(blank=True)
    design_reference_images = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['date', 'time']
        unique_together = ['shop', 'date', 'time']
        indexes = [
            models.Index(fields=['shop', 'date', 'status']),
        ]
    
    def __str__(self):
        return f"Consultation: {self.customer_name} on {self.date} at {self.time}"


# ==========================================
# BARBER DASHBOARD MODELS ✂️
# ==========================================

class WalkInEntry(models.Model):
    """
    Walk-in queue entry for barber shops.
    Customers can join the queue without a pre-booked appointment.
    """
    STATUS_CHOICES = [
        ('waiting', 'Waiting'),
        ('in_service', 'In Service'),
        ('completed', 'Completed'),
        ('no_show', 'No Show'),
        ('cancelled', 'Cancelled'),
    ]
    
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='walk_ins')
    customer_name = models.CharField(max_length=200)
    customer_phone = models.CharField(max_length=20, blank=True)
    customer_email = models.EmailField(blank=True)
    # Optional: link to registered user
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, blank=True, 
        related_name='walk_ins'
    )
    service = models.ForeignKey(
        'Service', 
        on_delete=models.SET_NULL, 
        null=True, blank=True,
        related_name='walk_ins'
    )
    
    position = models.PositiveIntegerField(default=0, help_text="Queue position")
    estimated_wait_minutes = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='waiting')
    notes = models.TextField(blank=True)
    
    joined_at = models.DateTimeField(auto_now_add=True)
    called_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['position', 'joined_at']
        verbose_name_plural = 'Walk-in entries'
        indexes = [
            models.Index(fields=['shop', 'status', 'joined_at']),
        ]
    
    def __str__(self):
        return f"{self.customer_name} - {self.status} (#{self.position})"


class LoyaltyProgram(models.Model):
    """
    Shop's loyalty program settings.
    One program per shop.
    """
    shop = models.OneToOneField(Shop, on_delete=models.CASCADE, related_name='loyalty_program')
    
    is_active = models.BooleanField(default=False)
    points_per_dollar = models.DecimalField(
        max_digits=5, decimal_places=2, default=1.00,
        help_text="Points earned per dollar spent"
    )
    points_for_redemption = models.PositiveIntegerField(
        default=100, 
        help_text="Points needed to redeem a reward"
    )
    reward_type = models.CharField(
        max_length=20,
        choices=[
            ('discount_percent', 'Discount (%)'),
            ('discount_fixed', 'Discount ($)'),
            ('free_service', 'Free Service'),
        ],
        default='discount_percent'
    )
    reward_value = models.DecimalField(
        max_digits=10, decimal_places=2, default=10.00,
        help_text="Discount percentage or fixed amount"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Loyalty Program for {self.shop.name}"


class LoyaltyPoints(models.Model):
    """
    Customer's loyalty points for a specific shop.
    """
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='loyalty_customers')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='loyalty_points'
    )
    
    points_balance = models.PositiveIntegerField(default=0)
    total_points_earned = models.PositiveIntegerField(default=0)
    total_points_redeemed = models.PositiveIntegerField(default=0)
    
    last_earned_at = models.DateTimeField(null=True, blank=True)
    last_redeemed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['shop', 'user']
        verbose_name_plural = 'Loyalty points'
    
    def __str__(self):
        return f"{self.user.name} - {self.points_balance} pts @ {self.shop.name}"
    
    def add_points(self, amount_spent, loyalty_program):
        """Add points based on amount spent"""
        points_earned = int(amount_spent * loyalty_program.points_per_dollar)
        self.points_balance += points_earned
        self.total_points_earned += points_earned
        self.last_earned_at = timezone.now()
        self.save()
        return points_earned
    
    def redeem_points(self, loyalty_program):
        """Redeem points for a reward"""
        if self.points_balance >= loyalty_program.points_for_redemption:
            self.points_balance -= loyalty_program.points_for_redemption
            self.total_points_redeemed += loyalty_program.points_for_redemption
            self.last_redeemed_at = timezone.now()
            self.save()
            return True, loyalty_program.reward_value
        return False, 0


# ==========================================
# NAIL TECH DASHBOARD MODELS 💅
# ==========================================

class StyleRequest(models.Model):
    """
    Client nail style requests for Nail Tech shops.
    Similar to DesignRequest but for nail styles.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('declined', 'Declined'),
        ('completed', 'Completed'),
    ]
    
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='style_requests')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='style_requests'
    )
    booking = models.ForeignKey(
        'payments.Booking',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='style_requests'
    )
    
    title = models.CharField(max_length=200, blank=True)
    description = models.TextField(help_text="Client's style description")
    nail_style_type = models.CharField(max_length=20, choices=Service.NAIL_STYLE_CHOICES, blank=True)
    nail_shape = models.CharField(max_length=20, choices=Service.NAIL_SHAPE_CHOICES, blank=True)
    color_preference = models.CharField(max_length=100, blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['shop', 'status']),
        ]
    
    def __str__(self):
        return f"Style Request: {self.user.name} - {self.nail_style_type or 'General'}"


class StyleRequestImage(models.Model):
    """Reference images for nail style requests"""
    style_request = models.ForeignKey(
        StyleRequest,
        on_delete=models.CASCADE,
        related_name='images'
    )
    image = models.ImageField(upload_to='style_requests/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Image for {self.style_request}"


# ==========================================
# MAKEUP ARTIST (MUA) DASHBOARD MODELS 💄
# ==========================================

class ClientBeautyProfile(models.Model):
    """Client skin tone and beauty preferences for MUA"""
    SKIN_TONE_CHOICES = [
        ('fair', 'Fair'),
        ('light', 'Light'),
        ('medium', 'Medium'),
        ('olive', 'Olive'),
        ('tan', 'Tan'),
        ('deep', 'Deep'),
    ]
    SKIN_TYPE_CHOICES = [
        ('normal', 'Normal'),
        ('oily', 'Oily'),
        ('dry', 'Dry'),
        ('combination', 'Combination'),
        ('sensitive', 'Sensitive'),
    ]
    UNDERTONE_CHOICES = [
        ('warm', 'Warm'),
        ('cool', 'Cool'),
        ('neutral', 'Neutral'),
    ]
    
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='beauty_profiles')
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='beauty_profiles'
    )
    
    skin_tone = models.CharField(max_length=20, choices=SKIN_TONE_CHOICES, blank=True)
    skin_type = models.CharField(max_length=20, choices=SKIN_TYPE_CHOICES, blank=True)
    undertone = models.CharField(max_length=20, choices=UNDERTONE_CHOICES, blank=True)
    allergies = models.TextField(blank=True, help_text="Product allergies or sensitivities")
    preferences = models.TextField(blank=True, help_text="General beauty preferences and notes")
    foundation_shade = models.CharField(max_length=50, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['shop', 'client']
        verbose_name_plural = 'Client beauty profiles'
    
    def __str__(self):
        return f"{self.client.name} - {self.skin_tone or 'Profile'} @ {self.shop.name}"


class ProductKitItem(models.Model):
    """MUA product kit checklist items"""
    CATEGORY_CHOICES = [
        ('foundation', 'Foundation'),
        ('concealer', 'Concealer'),
        ('powder', 'Powder'),
        ('blush', 'Blush'),
        ('bronzer', 'Bronzer'),
        ('highlighter', 'Highlighter'),
        ('eyeshadow', 'Eyeshadow'),
        ('eyeliner', 'Eyeliner'),
        ('mascara', 'Mascara'),
        ('brow', 'Brow Products'),
        ('lipstick', 'Lipstick'),
        ('lip_gloss', 'Lip Gloss'),
        ('primer', 'Primer'),
        ('setting_spray', 'Setting Spray'),
        ('brush', 'Brush'),
        ('sponge', 'Sponge/Applicator'),
        ('skincare', 'Skincare'),
        ('other', 'Other'),
    ]
    
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='product_kit')
    
    name = models.CharField(max_length=200)
    brand = models.CharField(max_length=100, blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    quantity = models.PositiveIntegerField(default=1)
    is_packed = models.BooleanField(default=False, help_text="Checked off in kit")
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['category', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.brand or 'No brand'}) - {self.shop.name}"


# ==========================================
# HAIRSTYLIST/LOCTICIAN DASHBOARD MODELS 💇‍♀️
# ==========================================

class ClientHairProfile(models.Model):
    """Client hair type, history, and preferences for hairstylists/locticians"""
    HAIR_TYPE_CHOICES = [
        ('1a', '1A - Fine Straight'),
        ('1b', '1B - Medium Straight'),
        ('1c', '1C - Coarse Straight'),
        ('2a', '2A - Fine Wavy'),
        ('2b', '2B - Medium Wavy'),
        ('2c', '2C - Coarse Wavy'),
        ('3a', '3A - Loose Curls'),
        ('3b', '3B - Springy Curls'),
        ('3c', '3C - Tight Curls'),
        ('4a', '4A - Soft Coils'),
        ('4b', '4B - Z-Pattern Coils'),
        ('4c', '4C - Tight Coils'),
    ]
    HAIR_TEXTURE_CHOICES = [
        ('fine', 'Fine'),
        ('medium', 'Medium'),
        ('coarse', 'Coarse'),
    ]
    HAIR_POROSITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
    ]
    
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='hair_profiles')
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='hair_profiles'
    )
    
    hair_type = models.CharField(max_length=10, choices=HAIR_TYPE_CHOICES, blank=True)
    hair_texture = models.CharField(max_length=20, choices=HAIR_TEXTURE_CHOICES, blank=True)
    hair_porosity = models.CharField(max_length=20, choices=HAIR_POROSITY_CHOICES, blank=True)
    natural_color = models.CharField(max_length=50, blank=True)
    current_color = models.CharField(max_length=50, blank=True)
    color_history = models.TextField(blank=True, help_text="Previous color treatments")
    chemical_history = models.TextField(blank=True, help_text="Relaxers, perms, keratin, etc.")
    scalp_condition = models.CharField(max_length=100, blank=True, help_text="Dry, oily, sensitive, etc.")
    allergies = models.TextField(blank=True, help_text="Product allergies or sensitivities")
    preferences = models.TextField(blank=True, help_text="Style preferences and notes")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['shop', 'client']
        verbose_name_plural = 'Client hair profiles'
    
    def __str__(self):
        return f"{self.client.name} - {self.get_hair_type_display() or 'Profile'} @ {self.shop.name}"


class ProductRecommendation(models.Model):
    """Product recommendations for clients from service providers (shared across niches)"""
    CATEGORY_CHOICES = [
        # Hair
        ('shampoo', 'Shampoo'),
        ('conditioner', 'Conditioner'),
        ('treatment', 'Treatment'),
        ('oil', 'Oil'),
        ('styling', 'Styling Product'),
        ('protectant', 'Heat Protectant'),
        ('leave_in', 'Leave-In'),
        ('mask', 'Hair Mask'),
        ('color', 'Color Product'),
        # Esthetician/Skincare
        ('cleanser', 'Cleanser'),
        ('serum', 'Serum'),
        ('moisturizer', 'Moisturizer'),
        ('sunscreen', 'Sunscreen'),
        ('exfoliant', 'Exfoliant'),
        ('toner', 'Toner'),
        ('eye_cream', 'Eye Cream'),
        # General
        ('tool', 'Tool/Accessory'),
        ('other', 'Other'),
    ]
    NICHE_CHOICES = [
        ('general', 'General'),
        ('hair', 'Hair'),
        ('esthetician', 'Esthetician'),
        ('massage', 'Massage'),
    ]
    
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='product_recommendations')
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='product_recommendations'
    )
    booking = models.ForeignKey(
        'payments.Booking',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='product_recommendations'
    )
    
    product_name = models.CharField(max_length=200)
    brand = models.CharField(max_length=100, blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    notes = models.TextField(blank=True, help_text="Usage instructions or notes")
    purchase_link = models.URLField(blank=True)
    
    # New fields for multi-niche support
    niche = models.CharField(max_length=20, choices=NICHE_CHOICES, default='general')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='created_recommendations'
    )
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.product_name} for {self.client.name}"


# ==========================================
# ESTHETICIAN/MASSAGE THERAPIST DASHBOARD 🧖
# ==========================================

class ClientSkinProfile(models.Model):
    """Client skin profile with skincare regimen (merged) for estheticians"""
    SKIN_TYPE_CHOICES = [
        ('normal', 'Normal'),
        ('dry', 'Dry'),
        ('oily', 'Oily'),
        ('combination', 'Combination'),
        ('sensitive', 'Sensitive'),
    ]
    
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='skin_profiles')
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='skin_profiles'
    )
    
    # Skin assessment
    skin_type = models.CharField(max_length=20, choices=SKIN_TYPE_CHOICES, blank=True)
    primary_concerns = models.JSONField(default=list, help_text="['acne', 'aging', 'pigmentation']")
    allergies = models.TextField(blank=True)
    sensitivities = models.TextField(blank=True)
    current_products = models.TextField(blank=True, help_text="Products client currently uses")
    
    # Regimen (merged from SkincareRegimen)
    morning_routine = models.JSONField(default=list, help_text="[{step, product, notes}]")
    evening_routine = models.JSONField(default=list)
    weekly_treatments = models.JSONField(default=list)
    regimen_notes = models.TextField(blank=True)
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['shop', 'client']
        verbose_name_plural = 'Client skin profiles'
    
    def __str__(self):
        return f"{self.client.name} - {self.get_skin_type_display() or 'Profile'} @ {self.shop.name}"


class HealthDisclosure(models.Model):
    """Health disclosure form for esthetician/massage services"""
    PRESSURE_CHOICES = [
        ('light', 'Light'),
        ('medium', 'Medium'),
        ('firm', 'Firm'),
        ('deep', 'Deep Tissue'),
    ]
    
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='health_disclosures')
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='health_disclosures'
    )
    booking = models.ForeignKey(
        'payments.Booking',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='health_disclosures'
    )
    
    # Medical information
    has_medical_conditions = models.BooleanField(default=False)
    conditions_detail = models.TextField(blank=True)
    current_medications = models.TextField(blank=True)
    allergies = models.TextField(blank=True)
    pregnant_or_nursing = models.BooleanField(default=False)
    recent_surgeries = models.TextField(blank=True)
    
    # Massage-specific
    pressure_preference = models.CharField(max_length=20, choices=PRESSURE_CHOICES, blank=True)
    areas_to_avoid = models.TextField(blank=True)
    areas_to_focus = models.TextField(blank=True)
    
    # Acknowledgment
    acknowledged = models.BooleanField(default=False)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='created_disclosures'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Health disclosures'
    
    def __str__(self):
        return f"Disclosure: {self.client.name} @ {self.shop.name}"


class TreatmentNote(models.Model):
    """Treatment notes per booking for esthetician/massage services"""
    TREATMENT_TYPE_CHOICES = [
        ('facial', 'Facial'),
        ('massage', 'Massage'),
        ('body', 'Body Treatment'),
        ('wax', 'Waxing'),
        ('lash', 'Lash/Brow'),
        ('peel', 'Chemical Peel'),
        ('microderm', 'Microdermabrasion'),
        ('wrap', 'Body Wrap'),
        ('scrub', 'Body Scrub'),
        ('other', 'Other'),
    ]
    
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='treatment_notes')
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='treatment_notes'
    )
    booking = models.OneToOneField(
        'payments.Booking',
        on_delete=models.CASCADE,
        related_name='treatment_note'
    )
    
    treatment_type = models.CharField(max_length=20, choices=TREATMENT_TYPE_CHOICES)
    products_used = models.TextField(blank=True)
    observations = models.TextField(blank=True)
    recommendations = models.TextField(blank=True)
    next_appointment_notes = models.TextField(blank=True)
    before_photo_url = models.URLField(blank=True)
    after_photo_url = models.URLField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_treatment_type_display()} - {self.client.name} ({self.booking.id})"


class RetailProduct(models.Model):
    """Retail products offered by shop for sale"""
    CATEGORY_CHOICES = [
        ('cleanser', 'Cleanser'),
        ('serum', 'Serum'),
        ('moisturizer', 'Moisturizer'),
        ('sunscreen', 'Sunscreen'),
        ('mask', 'Mask'),
        ('exfoliant', 'Exfoliant'),
        ('toner', 'Toner'),
        ('eye_cream', 'Eye Cream'),
        ('oil', 'Oil'),
        ('body_care', 'Body Care'),
        ('tool', 'Tool/Accessory'),
        ('other', 'Other'),
    ]
    
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='retail_products')
    
    name = models.CharField(max_length=200)
    brand = models.CharField(max_length=100, blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True)
    image_url = models.URLField(blank=True)
    in_stock = models.BooleanField(default=True)
    purchase_link = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['category', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.brand or 'No brand'}) - ${self.price}"
