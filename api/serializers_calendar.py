from rest_framework import serializers
from django.utils import timezone
from datetime import datetime, timezone as dt_timezone
from api.models import BlockedTime
from payments.models import Booking
from payments.utils.deposit import calculate_deposit_details

class CalendarEventSerializer(serializers.Serializer):
    """
    Unified serializer for calendar events (Bookings + BlockedTime).
    Output schema is consistent for UI rendering.
    """
    id = serializers.IntegerField()
    event_type = serializers.SerializerMethodField()  # "booking" or "blocked"
    title = serializers.SerializerMethodField()
    
    start_at = serializers.DateTimeField()
    end_at = serializers.DateTimeField()
    
    # Timezone helpers
    start_at_utc = serializers.SerializerMethodField()
    end_at_utc = serializers.SerializerMethodField()
    timezone_id = serializers.SerializerMethodField()
    
    # UI Status & Badges
    calendar_status = serializers.SerializerMethodField()
    badges = serializers.SerializerMethodField()
    
    # Details (nullable depending on type)
    provider = serializers.SerializerMethodField()
    customer = serializers.SerializerMethodField()
    service = serializers.SerializerMethodField()
    
    # Blocked specific
    blocked_reason = serializers.SerializerMethodField()
    note = serializers.SerializerMethodField()

    def get_event_type(self, obj):
        if isinstance(obj, BlockedTime):
            return "blocked"
        return "booking"

    def get_title(self, obj):
        if isinstance(obj, BlockedTime):
            title = "Blocked"
            if obj.note:
                title += f": {obj.note}"
            return title
        elif isinstance(obj, Booking):
            svc_title = obj.slot.service.title if obj.slot and obj.slot.service else "Service"
            cust_name = obj.user.name if obj.user and obj.user.name else "Guest"
            return f"{svc_title} - {cust_name}"
        return "Event"

    def get_blocked_reason(self, obj):
        if isinstance(obj, BlockedTime):
            return obj.reason
        return None

    def get_note(self, obj):
        if isinstance(obj, BlockedTime):
            return obj.note
        return None

    def get_start_at_utc(self, obj):
        # Allow obj to be dict or model
        dt = obj.get('start_at') if isinstance(obj, dict) else obj.start_at
        return dt.astimezone(dt_timezone.utc).isoformat()

    def get_end_at_utc(self, obj):
        dt = obj.get('end_at') if isinstance(obj, dict) else obj.end_at
        return dt.astimezone(dt_timezone.utc).isoformat()

    def get_timezone_id(self, obj):
        # Retrieve timezone from shop (if available) or settings
        # This assumes obj has a 'shop' relation or field
        shop = obj.get('shop') if isinstance(obj, dict) else getattr(obj, 'shop', None)
        if hasattr(shop, 'timezone'):
            return str(shop.timezone)
        # Fallback to current active timezone
        return str(timezone.get_current_timezone_name())

    def get_calendar_status(self, obj):
        """
        Derives the primary status color-driver.
        """
        if isinstance(obj, BlockedTime):
            return "BLOCKED"
            
        if isinstance(obj, Booking):
            status = obj.status
            if status == 'cancelled':
                return "CANCELED"
            if status == 'completed':
                return "COMPLETED"
            if status == 'no-show':
                return "NO_SHOW"
            
            # PENDING CHECK
            # 1. Deposit Required AND Not Paid
            shop = obj.shop
            payment = getattr(obj, 'payment', None)
            
            is_deposit_due = False
            if payment:
                # Use robust deposit util logic? 
                # Or trust existing payment fields? 
                # Logic: If shop requires deposit, check if payment is credited/succeeded.
                
                # Check 1: Is deposit required?
                # We can recalculate or rely on Payment.is_deposit (snapshot at creation)
                # Let's rely on Payment.is_deposit snapshot + deposit_status
                if payment.is_deposit and payment.deposit_status != 'credited':
                    is_deposit_due = True
                    
            if is_deposit_due:
                return "PENDING"
                
            # Future: Manual confirmation check (obj.requires_confirmation?)
            
            # If active and paid/no-deposit -> CONFIRMED
            return "CONFIRMED"

        return "UNKNOWN"

    def get_badges(self, obj):
        """
        Derives secondary badges list.
        """
        badges = []
        
        if isinstance(obj, BlockedTime):
            return badges # No badges for blocks usually
            
        if isinstance(obj, Booking):
            payment = getattr(obj, 'payment', None)
            
            # [PAID]
            # Succeeded = fully paid or deposit paid?
            # Client req: "Payment.status == 'succeeded' OR (deposit credited & remaining 0)"
            if payment:
                if payment.status == 'succeeded':
                    badges.append("PAID")
                elif payment.deposit_status == 'credited' and payment.remaining_amount == 0:
                    badges.append("PAID")
            
            # [DEP_DUE]
            # Deposit required but not credited
            if payment and payment.is_deposit and payment.deposit_status != 'credited':
                badges.append("DEP_DUE")
                
            # [FORMS]
            # Check Booking fields
            if getattr(obj, 'forms_required', False) and not getattr(obj, 'forms_completed', False):
                badges.append("FORMS")
                
            # [NEW]
            # First time customer check
            # We need to query history.
            # Ideally this is computed in View to avoid N+1, or we do a lightweight check here.
            # For performance, let's assume the view annotates it or we do a quick check.
            # Doing a DB query inside serializer is risky for lists.
            # Allow 'is_new_customer' to be passed in context or annotated.
            if getattr(obj, 'is_new_customer', False):
                badges.append("NEW")
            # If not annotated, we might skip or do a query (be careful)
            # Let's check context
            elif self.context.get('check_new_customer', False):
                # Perform query
                has_history = Booking.objects.filter(
                    shop=obj.shop,
                    user=obj.user,
                    status__in=['completed', 'active']
                ).exclude(id=obj.id).exists()
                if not has_history:
                    badges.append("NEW")

        return badges

    def get_provider(self, obj):
        if hasattr(obj, 'provider') and obj.provider:
            return {"id": obj.provider.id, "name": obj.provider.name}
        return None

    def get_customer(self, obj):
        if hasattr(obj, 'user') and obj.user:
            return {"id": obj.user.id, "name": obj.user.name or obj.user.email}
        return None

    def get_service(self, obj):
        if hasattr(obj, 'slot') and hasattr(obj.slot, 'service'):
            return {"id": obj.slot.service.id, "title": obj.slot.service.title}
        return None

    def to_representation(self, instance):
        """
        Polymorphic dispatch or manual dict construction based on instance type.
        """
        ret = super().to_representation(instance)
        
        # Inject event_type
        if isinstance(instance, BlockedTime):
            ret['event_type'] = 'blocked'
            ret['title'] = "Blocked" # or instance.note or reason
            if instance.note:
                ret['title'] += f": {instance.note}"
            ret['blocked_reason'] = instance.reason
            
        elif isinstance(instance, Booking):
            ret['event_type'] = 'booking'
            # Title is usually Service Name + Customer Name
            svc_title = instance.slot.service.title if instance.slot and instance.slot.service else "Service"
            cust_name = instance.user.first_name if instance.user else "Guest"
            ret['title'] = f"{svc_title} - {cust_name}"
            
        return ret
