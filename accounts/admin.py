from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User

class UserAdmin(BaseUserAdmin):
    model = User

    list_display = ("email", "role", "is_verified", "is_staff", "is_active")
    list_filter = ("role", "is_staff", "is_active", "is_verified")
    search_fields = ("email", "name")
    ordering = ("email",)

    # Fields shown when editing a user
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal Info", {"fields": ("name", "mobile_number", "profile_image")}),
        ("Role & Verification", {"fields": ("role", "is_verified")}),
        ("OTP Info", {"fields": ("otp", "otp_created_at")}),
        ("Permissions", {"fields": ("is_staff", "is_active", "is_superuser", "groups", "user_permissions")}),
    )

    readonly_fields = ("otp_created_at",)  # Show OTP created time as read-only

    # Fields shown when creating a user
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "password1", "password2", "role", "is_verified", "is_staff", "is_active"),
        }),
    )

admin.site.register(User, UserAdmin)
