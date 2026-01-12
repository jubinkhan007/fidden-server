from django.contrib import admin

from .models import (
    PerformanceAnalytics,
    Shop, 
    Service, 
    ServiceCategory, 
    RatingReview, 
    Promotion, 
    Slot, 
    SlotBooking, 
    ServiceWishlist,
    VerificationFile,
    Reply,
    ChatThread, 
    Message, 
    Device, 
    Notification,
    Revenue,
    Coupon,
    GlobalSettings,
    WaitlistEntry, 
    AutoFillLog,
    GalleryItem,
    # New Scheduling Models
    AvailabilityRuleSet,
    Provider,
    ProviderDayLock,
    AvailabilityException,
)
try:
    from .models import AIAutoFillSettings  # noqa: F401
except Exception:
    AIAutoFillSettings = None

admin.site.site_header = "Fidden Administration"
admin.site.site_title = "Fidden Admin Portal"
admin.site.index_title = "Welcome to Fidden Admin Dashboard"

class ServiceInline(admin.TabularInline):
    model = Service
    extra = 1

class VerificationFileInline(admin.TabularInline):
    model = VerificationFile
    extra = 1

@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'owner', 'address', 'location', 'capacity', 
        'status', 'default_is_deposit_required', 'get_subscription_plan'
    )
    list_filter = (
        'status', 'default_is_deposit_required', 
        'subscription__plan__name'
    )
    search_fields = ('name', 'owner__email', 'owner__name', 'address')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('owner', 'name', 'address', 'location', 'about_us', 'shop_img')
        }),
        ('Operational Settings', {
            'fields': (
                'capacity', 'start_at', 'close_at', 
                'break_start_time', 'break_end_time', 'close_days',
                # New rule-based fields
                'default_interval_minutes', 'access_hours', 'default_availability_ruleset',
                'use_rule_based_availability'
            )
        }),
        ('Deposit Settings', {
            'fields': ('default_is_deposit_required',),
            'description': 'Deposit settings - restricted by subscription plan for regular users'
        }),
        ('Cancellation Policy', {
            'fields': (
                'free_cancellation_hours', 'cancellation_fee_percentage', 
                'no_refund_hours'
            ),
            'description': 'Cancellation policy - Icon plan required for regular users'
        }),
        ('Status & Verification', {
            'fields': ('status',)
        }),
    )
    
    inlines = [ServiceInline, VerificationFileInline]
    
    def get_subscription_plan(self, obj):
        """Display current subscription plan"""
        if hasattr(obj, 'subscription') and obj.subscription.is_active:
            return obj.subscription.plan.name
        return 'No active subscription'
    get_subscription_plan.short_description = 'Subscription Plan'
    
    def get_readonly_fields(self, request, obj=None):
        """Superusers can modify all fields, regular staff have restrictions"""
        if request.user.is_superuser:
            return []  # Only verification status is readonly for superusers
        
         # Fields controlled by plan
        deposit_fields = ['default_is_deposit_required',]
        cancellation_fields = ['free_cancellation_hours', 'cancellation_fee_percentage', 'no_refund_hours']

        # On add view (obj is None), be conservative like Foundation
        if obj is None:
            return deposit_fields + cancellation_fields

        
        # Determine current plan (if any)
        plan_name = None
        if getattr(obj, 'subscription', None) and obj.subscription.is_active and obj.subscription.plan:
            plan_name = obj.subscription.plan.name

        # Foundation: no modification on deposit/cancellation
        if plan_name == 'Foundation':
            return deposit_fields + cancellation_fields

        # Momentum: only deposit_amount editable; keep others readonly
        if plan_name == 'Momentum':
            return ['default_is_deposit_required'] + cancellation_fields

        # Icon (or anything else): full control except verification
        return []

        
        # Regular staff cannot modify deposit/cancellation settings
        return [
            'default_is_deposit_required',
            'free_cancellation_hours', 'cancellation_fee_percentage', 'no_refund_hours'
        ]
    # list_display = ('name', 'owner', 'address', 'location', 'capacity')
    # inlines = [ServiceInline, VerificationFileInline]

@admin.register(VerificationFile)
class VerificationFileAdmin(admin.ModelAdmin):
    list_display = ('id', 'shop', 'file', 'uploaded_at')
    list_filter = ('uploaded_at', 'shop')
    search_fields = ('shop__name', 'file')
    ordering = ('-uploaded_at',)

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'shop', 'category', 'price', 'discount_price',
        'is_deposit_required', 'deposit_amount', 'deposit_type'
    )
    list_filter = (
        'shop', 'category', 'is_deposit_required', 
        'deposit_type', 'is_active'
    )
    search_fields = ('title', 'shop__name', 'description')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'shop', 'category', 'description', 'service_img')
        }),
        ('Pricing', {
            'fields': ('price', 'discount_price')
        }),
        ('Service Settings', {
            'fields': ('duration', 'capacity', 'is_active')
        }),
        ('Deposit Settings', {
            'fields': (
                'is_deposit_required', 'deposit_type', 
                'deposit_amount', 'deposit_percentage'
            ),
            'description': 'Deposit settings - restricted by shop subscription plan for regular users'
        }),
    )
    
    def get_readonly_fields(self, request, obj=None):
        """Superusers can modify all fields, regular staff have deposit restrictions"""
        if request.user.is_superuser:
            return []  # Superusers can edit everything
        
        # Regular staff cannot modify deposit settings
        return [
            'is_deposit_required', 'deposit_type', 
            'deposit_amount', 'deposit_percentage'
        ]
    
    def save_model(self, request, obj, form, change):
        """Add admin override for superuser deposit changes"""
        if request.user.is_superuser and change:
            changed_fields = form.changed_data
            deposit_fields = [
                'is_deposit_required', 'deposit_type', 
                'deposit_amount', 'deposit_percentage'
            ]
            
            if any(field in changed_fields for field in deposit_fields):
                # Log superuser override of subscription restrictions
                pass
        
        super().save_model(request, obj, form, change)

@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'sc_img',)

class ReplyInline(admin.TabularInline):
    model = Reply
    extra = 1

@admin.register(RatingReview)
class RatingReviewAdmin(admin.ModelAdmin):
    list_display = ('id', 'shop', 'service', 'user_display', 'rating', 'created_at')
    list_filter = ('rating', 'shop', 'service', 'created_at')
    search_fields = ('review', 'user__username', 'user__email')
    ordering = ('-created_at',)
    inlines =[ReplyInline]

    def user_display(self, obj):
        if obj.user:
            return obj.user.name or "Anonymous"
        return "Anonymous"
    user_display.short_description = "User"

@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ('title', 'subtitle', 'amount', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('title', 'subtitle')
    ordering = ('-created_at',)

#  Slots
@admin.register(Slot)
class SlotAdmin(admin.ModelAdmin):
    list_display = ("shop", "service", "start_time", "end_time", "capacity_left")
    list_filter = ("shop", "service", "start_time")
    search_fields = ("shop__name", "service__title")
    ordering = ("start_time",)


#  Slot Bookings
@admin.register(SlotBooking)
class SlotBookingAdmin(admin.ModelAdmin):
    list_display = ("user", "shop", "service", "slot", "status", "payment_status", "start_time", "end_time")
    list_filter = ("status", "shop", "service", "start_time")
    search_fields = ("user__username", "shop__name", "service__title")
    ordering = ("-start_time",)

@admin.register(ServiceWishlist)
class ServiceWishlistAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'service', 'created_at')
    list_filter = ('created_at', 'user')
    search_fields = ('user__username', 'service__title')
    ordering = ('-created_at',)

@admin.register(ChatThread)
class ChatThreadAdmin(admin.ModelAdmin):
    list_display = ('id', 'shop', 'user', 'created_at')
    list_filter = ('created_at', 'shop')
    search_fields = ('user__username', 'shop__name')
    ordering = ('-created_at',)

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'thread', 'sender', 'is_read', 'timestamp')
    list_filter = ('is_read', 'timestamp')
    search_fields = ('sender__username', 'content')
    ordering = ('-timestamp',)

@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'device_type', 'device_token', 'created_at', 'updated_at')
    list_filter = ('device_type', 'created_at')
    search_fields = ('user__username', 'device_token')
    ordering = ('-created_at',)

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'recipient', 'message', 'notification_type', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('recipient__username', 'message')
    ordering = ('-created_at',)

@admin.register(Revenue)
class RevenueAdmin(admin.ModelAdmin):
    list_display = ('shop', 'revenue', 'timestamp')
    list_filter = ('shop', 'timestamp')             
    search_fields = ('shop__name',)                
    ordering = ('-timestamp',)         

@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = (
        "id", "code", "shop", "display_services", 
        "amount", "discount_type", "validity_date", 
        "is_active", "max_usage_per_user", "created_at"
    )
    list_filter = ("shop", "in_percentage", "is_active", "validity_date", "created_at")
    search_fields = ("code", "shop__name", "services__title")
    ordering = ("-created_at",)
    filter_horizontal = ("services",)  # nice UI for ManyToMany

    readonly_fields = ("created_at", "updated_at", "discount_type")

    fieldsets = (
        ("Coupon Details", {
            "fields": ("code", "description", "shop", "services")
        }),
        ("Discount Settings", {
            "fields": ("amount", "in_percentage", "discount_type")
        }),
        ("Validity", {
            "fields": ("validity_date", "is_active", "max_usage_per_user")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at")
        }),
    )

    def display_services(self, obj):
        """Show related services as comma-separated titles."""
        return ", ".join(service.title for service in obj.services.all())
    display_services.short_description = "Services"             


## new default value settings for admin which is gonna apply for all shop


# Add this at the end of admin.py
@admin.register(GlobalSettings)
class GlobalSettingsAdmin(admin.ModelAdmin):
    list_display = (
    'default_deposit_required',
    'default_deposit_percentage',
    'default_free_cancellation_hours',
    'default_cancellation_fee_percentage',
    'default_no_refund_hours',
    'updated_at',
    )
    search_fields = ()
    ordering = ('-updated_at',)

    def has_add_permission(self, request):
        # Only allow one settings instance
        return not GlobalSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # Don't allow deletion
        return False
    

@admin.register(PerformanceAnalytics)
class PerformanceAnalyticsAdmin(admin.ModelAdmin):
    list_display = ('shop', 'total_revenue', 'total_bookings', 'updated_at')
    search_fields = ('shop__name',)
if AIAutoFillSettings:
    @admin.register(AIAutoFillSettings)
    class AIAutoFillSettingsAdmin(admin.ModelAdmin):
        list_display = ('shop', 'is_active', 'no_show_window_minutes')
        list_filter = ('is_active',)
        search_fields = ('shop__name',)

@admin.register(WaitlistEntry)
class WaitlistEntryAdmin(admin.ModelAdmin):
    list_display = ('user', 'shop', 'service', 'created_at', 'opted_in_offers')
    list_filter = ('shop', 'opted_in_offers')
    search_fields = ('user__email', 'shop__name')

@admin.register(AutoFillLog)
class AutoFillLogAdmin(admin.ModelAdmin):
    list_display = ('shop', 'status', 'revenue_recovered', 'created_at')
    list_filter = ('status', 'shop')
    readonly_fields = ('original_booking', 'filled_by_booking')


@admin.register(GalleryItem)
class GalleryItemAdmin(admin.ModelAdmin):
    list_display = ('shop', 'caption', 'service', 'category_tag', 'is_public', 'created_at')
    list_filter = ('is_public', 'category_tag', 'shop')
    search_fields = ('shop__name', 'caption', 'category_tag')
    readonly_fields = ('thumbnail', 'created_at')
    raw_id_fields = ('shop', 'service')

# ---------------------------------------------
# NEW SCHEDULING SYSTEM ADMIN
# ---------------------------------------------

@admin.register(AvailabilityRuleSet)
class AvailabilityRuleSetAdmin(admin.ModelAdmin):
    list_display = ('name', 'timezone', 'interval_minutes', 'created_at')
    search_fields = ('name',)
    list_filter = ('timezone', 'interval_minutes')

@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ('name', 'shop', 'provider_type', 'is_active', 'allow_any_provider_booking', 'max_concurrent_processing_jobs')
    list_filter = ('shop', 'provider_type', 'is_active', 'allow_any_provider_booking')
    search_fields = ('name', 'shop__name', 'user__email')
    filter_horizontal = ('services',)
    
    fieldsets = (
        ('Identity', {
            'fields': ('shop', 'user', 'name', 'provider_type', 'is_active', 'profile_image')
        }),
        ('Scheduling Config', {
            'fields': ('availability_ruleset', 'services', 'allow_any_provider_booking')
        }),
        ('Concurrency Control', {
            'fields': ('max_concurrent_processing_jobs',),
            'description': 'Controls how many processing-phase bookings (e.g. hair processing) can run simultaneously.'
        }),
    )

@admin.register(AvailabilityException)
class AvailabilityExceptionAdmin(admin.ModelAdmin):
    list_display = ('provider', 'date', 'is_closed', 'note')
    list_filter = ('date', 'is_closed', 'provider__shop')
    search_fields = ('provider__name', 'note')

@admin.register(ProviderDayLock)
class ProviderDayLockAdmin(admin.ModelAdmin):
    list_display = ('shop', 'provider', 'date')
    list_filter = ('date', 'shop', 'provider')
    search_fields = ('shop__name', 'provider__name')
    readonly_fields = ('shop', 'provider', 'date')