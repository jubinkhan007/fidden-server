from django.db import models
from django.conf import settings
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q
import uuid



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
    # 🆕 Break time fields
    break_start_time = models.TimeField(blank=True, null=True)
    break_end_time = models.TimeField(blank=True, null=True)
    about_us = models.TextField(blank=True, null=True)
    shop_img = models.ImageField(upload_to='shop/', blank=True, null=True)

    close_days = models.JSONField(
        default=list,
        blank=True,
        help_text="List of closed days (e.g., ['monday', 'tuesday'])"
    )

    # ✅ new field
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="pending"
    )
    free_cancellation_hours = models.PositiveIntegerField(default=24)
    cancellation_fee_percentage = models.PositiveIntegerField(default=50)
    no_refund_hours = models.PositiveIntegerField(default=4)


    is_verified = models.BooleanField(default=False)  # renamed (typo fix)

    def save(self, *args, **kwargs):
        # Auto-update is_verified based on status
        if self.status == "verified":
            self.is_verified = True
        else:
            self.is_verified = False
        super().save(*args, **kwargs)

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
        "payments.Booking",   # ✅ each booking can have only one review
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
        return f"{self.shop.name} · {self.service.title} · {timezone.localtime(self.start_time)}"

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
        return f"{self.user} → {self.service.title} @ {self.shop.name} ({timezone.localtime(self.start_time)})"


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