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
    # Tattoo Artist Models
    DesignRequest,
    DesignRequestImage,
    Consultation,
    IDVerificationRequest,
    ConsentFormTemplate,
    SignedConsentForm,
    # Barber Dashboard Models
    WalkInEntry,
    LoyaltyProgram,
    LoyaltyPoints,
    # Nail Tech Dashboard Models
    StyleRequest,
    StyleRequestImage,
    # MUA Dashboard Models
    ClientBeautyProfile,
    ProductKitItem,
    # Hairstylist Dashboard Models
    ClientHairProfile,
    ProductRecommendation,
    # Esthetician Dashboard Models
    ClientSkinProfile,
    HealthDisclosure,
    TreatmentNote,
    RetailProduct,
    # Massage Therapist Dashboard Models
    ClientMassageProfile,
    SessionNote,
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

# ==========================================
# TATTOO ARTIST INLINES
# ==========================================

class DesignRequestImageInline(admin.TabularInline):
    model = DesignRequestImage
    extra = 1
    readonly_fields = ['created_at']

class DesignRequestInline(admin.StackedInline):
    model = DesignRequest
    extra = 0
    show_change_link = True
    fields = ['user', 'description', 'placement', 'size_approx', 'status', 'created_at']
    readonly_fields = ['created_at']  # User is now editable
    raw_id_fields = ['user']  # Use popup selector for user

class ConsultationInline(admin.TabularInline):
    model = Consultation
    extra = 0
    fields = ['customer_name', 'customer_email', 'date', 'time', 'status', 'notes']

class IDVerificationInline(admin.TabularInline):
    model = IDVerificationRequest
    extra = 0
    fields = ['user', 'status', 'front_image', 'back_image', 'created_at']
    readonly_fields = ['user', 'created_at']

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
    
    inlines = [
        ServiceInline, VerificationFileInline,
        # Tattoo Artist Inlines
        DesignRequestInline, ConsultationInline, IDVerificationInline
    ]
    
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


# ==========================================
# TATTOO ARTIST ADMIN VIEWS
# ==========================================

@admin.register(DesignRequest)
class DesignRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_user_name', 'shop', 'placement', 'size_approx', 'status', 'created_at')
    list_filter = ('status', 'shop', 'created_at')
    search_fields = ('user__name', 'user__email', 'shop__name', 'description', 'placement')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('shop', 'user', 'booking')
    inlines = [DesignRequestImageInline]
    
    fieldsets = (
        ('Client Info', {
            'fields': ('shop', 'user', 'booking')
        }),
        ('Design Details', {
            'fields': ('description', 'placement', 'size_approx', 'status')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_user_name(self, obj):
        return obj.user.name if obj.user else '-'
    get_user_name.short_description = 'Client Name'


@admin.register(Consultation)
class ConsultationAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer_name', 'shop', 'date', 'time', 'duration_minutes', 'status')
    list_filter = ('status', 'shop', 'date')
    search_fields = ('customer_name', 'customer_email', 'shop__name', 'notes')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Shop', {
            'fields': ('shop',)
        }),
        ('Customer Info', {
            'fields': ('customer_name', 'customer_email', 'customer_phone')
        }),
        ('Appointment', {
            'fields': ('date', 'time', 'duration_minutes', 'status')
        }),
        ('Notes', {
            'fields': ('notes', 'design_reference_images')
        }),
    )


@admin.register(IDVerificationRequest)
class IDVerificationRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_user_name', 'shop', 'status', 'created_at')
    list_filter = ('status', 'shop', 'created_at')
    search_fields = ('user__name', 'user__email', 'shop__name')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('shop', 'user', 'booking')
    
    def get_user_name(self, obj):
        return obj.user.name if obj.user else '-'
    get_user_name.short_description = 'Client'


@admin.register(ConsentFormTemplate)
class ConsentFormTemplateAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'shop', 'is_default', 'created_at')
    list_filter = ('is_default', 'shop')
    search_fields = ('title', 'shop__name', 'content')


@admin.register(SignedConsentForm)
class SignedConsentFormAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_user_name', 'get_template_title', 'signed_at')
    list_filter = ('template__shop', 'signed_at')
    search_fields = ('user__name', 'user__email', 'template__title')
    raw_id_fields = ('user', 'template', 'booking')
    
    def get_user_name(self, obj):
        return obj.user.name if obj.user else '-'
    get_user_name.short_description = 'Client'
    
    def get_template_title(self, obj):
        return obj.template.title if obj.template else '-'
    get_template_title.short_description = 'Form Template'


# ==========================================
# BARBER DASHBOARD ADMIN
# ==========================================

@admin.register(WalkInEntry)
class WalkInEntryAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer_name', 'shop', 'service', 'position', 'status', 'payment_method', 'amount_paid', 'joined_at')
    list_filter = ('status', 'shop', 'joined_at', 'payment_method')
    search_fields = ('customer_name', 'customer_phone', 'customer_email', 'shop__name')
    readonly_fields = ('joined_at', 'called_at', 'completed_at', 'slot_booking')
    raw_id_fields = ('shop', 'user', 'service', 'slot_booking')
    ordering = ['shop', 'position', '-joined_at']


@admin.register(LoyaltyProgram)
class LoyaltyProgramAdmin(admin.ModelAdmin):
    list_display = ('id', 'shop', 'is_active', 'points_per_dollar', 'points_for_redemption', 'reward_type')
    list_filter = ('is_active', 'reward_type')
    search_fields = ('shop__name',)
    raw_id_fields = ('shop',)


@admin.register(LoyaltyPoints)
class LoyaltyPointsAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_user_name', 'shop', 'points_balance', 'total_points_earned', 'total_points_redeemed')
    list_filter = ('shop',)
    search_fields = ('user__name', 'user__email', 'shop__name')
    raw_id_fields = ('shop', 'user')
    readonly_fields = ('total_points_earned', 'total_points_redeemed', 'last_earned_at', 'last_redeemed_at')
    
    def get_user_name(self, obj):
        return obj.user.name if obj.user else '-'
    get_user_name.short_description = 'Customer'


# ==========================================
# NAIL TECH DASHBOARD ADMIN 💅
# ==========================================

class StyleRequestImageInline(admin.TabularInline):
    model = StyleRequestImage
    extra = 1
    readonly_fields = ['uploaded_at']


@admin.register(StyleRequest)
class StyleRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_user_name', 'shop', 'nail_style_type', 'nail_shape', 'status', 'created_at')
    list_filter = ('status', 'nail_style_type', 'nail_shape', 'shop')
    search_fields = ('user__name', 'user__email', 'shop__name', 'title', 'description')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('shop', 'user', 'booking')
    inlines = [StyleRequestImageInline]
    
    fieldsets = (
        ('Client Info', {
            'fields': ('shop', 'user', 'booking')
        }),
        ('Style Details', {
            'fields': ('title', 'description', 'nail_style_type', 'nail_shape', 'color_preference', 'status')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_user_name(self, obj):
        return obj.user.name if obj.user else '-'
    get_user_name.short_description = 'Client'


# ==========================================
# MUA DASHBOARD ADMIN 💄
# ==========================================

@admin.register(ClientBeautyProfile)
class ClientBeautyProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_client_name', 'shop', 'skin_tone', 'skin_type', 'undertone', 'created_at')
    list_filter = ('skin_tone', 'skin_type', 'undertone', 'shop')
    search_fields = ('client__name', 'client__email', 'shop__name', 'foundation_shade')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('shop', 'client')
    
    fieldsets = (
        ('Client Info', {
            'fields': ('shop', 'client')
        }),
        ('Skin Profile', {
            'fields': ('skin_tone', 'skin_type', 'undertone', 'foundation_shade')
        }),
        ('Notes', {
            'fields': ('allergies', 'preferences')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_client_name(self, obj):
        return obj.client.name if obj.client else '-'
    get_client_name.short_description = 'Client'


@admin.register(ProductKitItem)
class ProductKitItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'brand', 'category', 'quantity', 'is_packed', 'shop')
    list_filter = ('category', 'is_packed', 'shop')
    search_fields = ('name', 'brand', 'shop__name')
    list_editable = ('is_packed', 'quantity')
    readonly_fields = ('created_at',)


# ==========================================
# HAIRSTYLIST DASHBOARD ADMIN 💇‍♀️
# ==========================================

@admin.register(ClientHairProfile)
class ClientHairProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_client_name', 'shop', 'hair_type', 'hair_texture', 'current_color', 'created_at')
    list_filter = ('hair_type', 'hair_texture', 'hair_porosity', 'shop')
    search_fields = ('client__name', 'client__email', 'shop__name', 'natural_color', 'current_color')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('shop', 'client')
    
    fieldsets = (
        ('Client Info', {
            'fields': ('shop', 'client')
        }),
        ('Hair Profile', {
            'fields': ('hair_type', 'hair_texture', 'hair_porosity', 'natural_color', 'current_color', 'scalp_condition')
        }),
        ('History', {
            'fields': ('color_history', 'chemical_history')
        }),
        ('Notes', {
            'fields': ('allergies', 'preferences')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_client_name(self, obj):
        return obj.client.name if obj.client else '-'
    get_client_name.short_description = 'Client'


@admin.register(ProductRecommendation)
class ProductRecommendationAdmin(admin.ModelAdmin):
    list_display = ('id', 'product_name', 'brand', 'category', 'niche', 'get_client_name', 'shop', 'is_active', 'created_at')
    list_filter = ('category', 'niche', 'is_active', 'shop')
    search_fields = ('product_name', 'brand', 'client__name', 'shop__name')
    readonly_fields = ('created_at',)
    raw_id_fields = ('shop', 'client', 'booking', 'created_by')
    
    def get_client_name(self, obj):
        return obj.client.name if obj.client else '-'
    get_client_name.short_description = 'Client'


# ==========================================
# ESTHETICIAN DASHBOARD ADMIN 🧖
# ==========================================

@admin.register(ClientSkinProfile)
class ClientSkinProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_client_name', 'shop', 'skin_type', 'created_at')
    list_filter = ('skin_type', 'shop')
    search_fields = ('client__name', 'client__email', 'shop__name')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('shop', 'client')
    
    def get_client_name(self, obj):
        return obj.client.name if obj.client else '-'
    get_client_name.short_description = 'Client'


@admin.register(HealthDisclosure)
class HealthDisclosureAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_client_name', 'shop', 'has_medical_conditions', 'pregnant_or_nursing', 'acknowledged', 'created_at')
    list_filter = ('has_medical_conditions', 'pregnant_or_nursing', 'acknowledged', 'shop')
    search_fields = ('client__name', 'client__email', 'shop__name')
    readonly_fields = ('created_at', 'updated_at', 'acknowledged_at')
    raw_id_fields = ('shop', 'client', 'booking', 'created_by')
    
    def get_client_name(self, obj):
        return obj.client.name if obj.client else '-'
    get_client_name.short_description = 'Client'


@admin.register(TreatmentNote)
class TreatmentNoteAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_client_name', 'treatment_type', 'booking', 'shop', 'created_at')
    list_filter = ('treatment_type', 'shop')
    search_fields = ('client__name', 'shop__name', 'observations', 'recommendations')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('shop', 'client', 'booking')
    
    def get_client_name(self, obj):
        return obj.client.name if obj.client else '-'
    get_client_name.short_description = 'Client'


@admin.register(RetailProduct)
class RetailProductAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'brand', 'category', 'price', 'in_stock', 'is_active', 'shop')
    list_filter = ('category', 'in_stock', 'is_active', 'shop')
    search_fields = ('name', 'brand', 'shop__name')
    readonly_fields = ('created_at',)
    list_editable = ('in_stock', 'is_active', 'price')


# ==========================================
# MASSAGE THERAPIST DASHBOARD ADMIN 💆
# ==========================================

@admin.register(ClientMassageProfile)
class ClientMassageProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_client_name', 'shop', 'pressure_preference', 'has_injuries', 'has_chronic_conditions', 'created_at')
    list_filter = ('pressure_preference', 'has_injuries', 'has_chronic_conditions', 'shop')
    search_fields = ('client__name', 'client__email', 'shop__name')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('shop', 'client')
    
    def get_client_name(self, obj):
        return obj.client.name if obj.client else '-'
    get_client_name.short_description = 'Client'


@admin.register(SessionNote)
class SessionNoteAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_client_name', 'technique_used', 'booking', 'duration_minutes', 'shop', 'created_at')
    list_filter = ('technique_used', 'shop')
    search_fields = ('client__name', 'shop__name', 'tension_observations', 'recommendations')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('shop', 'client', 'booking')
    
    def get_client_name(self, obj):
        return obj.client.name if obj.client else '-'
    get_client_name.short_description = 'Client'


# ---------------------------------------------
# NEW SCHEDULING SYSTEM ADMIN
# ---------------------------------------------

@admin.register(AvailabilityRuleSet)
class AvailabilityRuleSetAdmin(admin.ModelAdmin):
    list_display = ('name', 'timezone', 'interval_minutes', 'created_at')
    search_fields = ('name',)
    list_filter = ('timezone', 'interval_minutes')
    fieldsets = (
        ('Basic Settings', {
            'fields': ('name', 'timezone', 'interval_minutes')
        }),
        ('Schedule Rules', {
            'fields': ('weekly_rules', 'breaks'),
            'description': 'Define base weekly availability and regular breaks (JSON structure).'
        })
    )

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
            'description': 'Controls how many processing-phase services (e.g. hair processing) this provider can handle simultaneously. Default is 1.'
        }),
    )

@admin.register(AvailabilityException)
class AvailabilityExceptionAdmin(admin.ModelAdmin):
    list_display = ('provider', 'date', 'is_closed', 'note')
    list_filter = ('date', 'is_closed', 'provider__shop')
    search_fields = ('provider__name', 'note')
    date_hierarchy = 'date'
    
    fieldsets = (
        ('Exception Details', {
            'fields': ('provider', 'date', 'note')
        }),
        ('Overrides', {
            'fields': ('is_closed', 'override_rules', 'override_breaks'),
            'description': 'Set is_closed=True to block the day. Otherwise, provide specific start/end times in override_rules.'
        })
    )

@admin.register(ProviderDayLock)
class ProviderDayLockAdmin(admin.ModelAdmin):
    list_display = ('shop', 'provider', 'date')
    list_filter = ('date', 'shop', 'provider')
    search_fields = ('shop__name', 'provider__name')
    readonly_fields = ('shop', 'provider', 'date')
    date_hierarchy = 'date'

