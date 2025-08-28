from django.db import models
from django.conf import settings
from datetime import timedelta
from django.utils import timezone


class Shop(models.Model):
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
    about_us = models.TextField(blank=True, null=True)
    shop_img = models.ImageField(upload_to='shop/', blank=True, null=True)

    # ✅ changed from open_days → close_days
    close_days = models.JSONField(
        default=list,
        help_text="List of closed days (e.g., ['monday', 'tuesday'])"
    )

    def __str__(self):
        return self.name


class ServiceCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Service(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='services')
    category = models.ForeignKey(ServiceCategory, on_delete=models.CASCADE, related_name='services')
    title = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
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
    STATUS_CHOICES = [('confirmed', 'Confirmed'), ('cancelled', 'Cancelled')]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='slot_bookings')
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='slot_bookings')
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='slot_bookings')
    slot = models.ForeignKey(Slot, on_delete=models.CASCADE, related_name='bookings')
    start_time = models.DateTimeField(db_index=True)
    end_time = models.DateTimeField()
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='confirmed')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_time']
        indexes = [
            models.Index(fields=['shop', 'start_time', 'end_time']),
            models.Index(fields=['service', 'start_time']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['user', 'slot'], name='uniq_user_slot')
        ]

    def __str__(self):
        return f"{self.user} → {self.service.title} @ {self.shop.name} ({timezone.localtime(self.start_time)})"

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