from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User

class UserAdmin(BaseUserAdmin):
    model = User
    list_display = ("email", "role", "is_staff", "is_active", "is_verified")
    list_filter = ("role", "is_staff", "is_active", "is_verified")
    search_fields = ("email",)
    ordering = ("email",)

    fieldsets = (
        (None, {"fields": ("email", "password", "role", "is_verified", "otp", "otp_created_at")}),
        ("Permissions", {"fields": ("is_staff", "is_active", "is_superuser", "groups", "user_permissions")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "password1", "password2", "role", "is_verified", "is_staff", "is_active"),
        }),
    )

admin.site.register(User, UserAdmin)
