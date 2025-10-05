import random
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from datetime import timedelta
from django.core.validators import RegexValidator

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, role="user", **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, role=role, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, role="admin", **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = (
        ('owner', 'Owner'),
        ('user', 'User'),
    )

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="user")
    is_verified = models.BooleanField(default=False)
    otp = models.CharField(max_length=6, blank=True, null=True)
    otp_created_at = models.DateTimeField(blank=True, null=True)

    # Profile fields
    name = models.CharField(max_length=100, blank=True, null=True)
    mobile_number = models.CharField(
        max_length=15,
        blank=True,
        null=True,
        validators=[RegexValidator(r'^\+?1?\d{9,15}$', 'Enter a valid mobile number.')]
    )
    profile_image = models.ImageField(upload_to='profile_images/', blank=True, null=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email

    # OTP methods
    def generate_otp(self):
        """Generate and save a 6-digit OTP"""
        from accounts.services.utils import generate_otp
        self.otp = generate_otp()
        self.otp_created_at = timezone.now()
        self.save()
        return self.otp

    def is_otp_valid(self, otp, validity_minutes=5):
        """Check OTP match and expiry"""
        if self.otp != otp:
            return False
        if not self.otp_created_at or timezone.now() > self.otp_created_at + timedelta(minutes=validity_minutes):
            return False
        return True
