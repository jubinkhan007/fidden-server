# Barber Dashboard Serializers
from rest_framework import serializers
from payments.models import Booking

class BarberAppointmentSerializer(serializers.ModelSerializer):
    """Serializer for today's appointments in Barber Dashboard"""
    customer_name = serializers.CharField(source='user.name', read_only=True)
    customer_email = serializers.EmailField(source='user.email', read_only=True)
    service_name = serializers.CharField(source='slot.service.title', read_only=True)
    service_duration = serializers.IntegerField(source='slot.service.duration', read_only=True)
    service_niche = serializers.SerializerMethodField()
    start_time = serializers.DateTimeField(source='slot.start_time', read_only=True)
    end_time = serializers.DateTimeField(source='slot.end_time', read_only=True)
    shop_timezone = serializers.SerializerMethodField()
    
    class Meta:
        model = Booking
        fields = [
            'id',
            'customer_name',
            'customer_email',
            'service_name',
            'service_duration',
            'service_niche',
            'start_time',
            'end_time',
            'status',
            'shop_timezone',
            'created_at'
        ]
    
    def get_shop_timezone(self, obj):
        """Return shop's IANA timezone for client-side conversion."""
        from api.utils.timezone_helpers import get_valid_iana_timezone
        if obj.shop:
            return get_valid_iana_timezone(obj.shop.time_zone)
        return "America/New_York"
    
    def to_representation(self, instance):
        """
        Ensure all times are in UTC with Z suffix - consistent with ownerBookingSerializer.
        """
        from api.utils.timezone_helpers import to_utc_iso
        rep = super().to_representation(instance)
        
        # Convert start_time and end_time to UTC
        if instance.slot and instance.slot.start_time:
            rep['start_time'] = to_utc_iso(instance.slot.start_time)
        if instance.slot and instance.slot.end_time:
            rep['end_time'] = to_utc_iso(instance.slot.end_time)
        
        # Created time in UTC
        if instance.created_at:
            rep['created_at'] = to_utc_iso(instance.created_at)
        
        return rep
    
    def get_service_niche(self, obj):
        """Determine the niche based on service type fields or category"""
        if obj.slot and obj.slot.service:
            service = obj.slot.service
            
            # Check service-specific type fields first
            if getattr(service, 'look_type', None):
                return 'makeup_artist'
            if getattr(service, 'nail_style_type', None):
                return 'nail_tech'
            if getattr(service, 'hair_service_type', None):
                return 'hairstylist'
            if getattr(service, 'esthetician_service_type', None):
                return 'esthetician'
            
            # Fallback: Check category for niche inference
            if service.category:
                cat_name = service.category.name.lower()
                # Check title too for better matching
                title = service.title.lower() if service.title else ''
                
                if any(k in cat_name or k in title for k in ['makeup', 'make up', 'mua', 'bridal', 'glam']):
                    return 'makeup_artist'
                if any(k in cat_name or k in title for k in ['nail', 'manicure', 'pedicure', 'gel', 'acrylic']):
                    return 'nail_tech'
                if any(k in cat_name or k in title for k in ['barber', 'haircut', 'fade', 'beard', 'shave']):
                    return 'barber'
                if any(k in cat_name or k in title for k in ['tattoo', 'piercing', 'ink', 'tat']):
                    return 'tattoo_artist'
                if any(k in cat_name or k in title for k in ['hair', 'style', 'color', 'loc', 'braid']):
                    return 'hairstylist'
                if any(k in cat_name or k in title for k in ['massage', 'deep tissue', 'swedish', 'hot stone']):
                    return 'massage_therapist'
                if any(k in cat_name or k in title for k in ['facial', 'skin', 'peel', 'wax', 'spa']):
                    return 'esthetician'
        return 'general'


class BarberNoShowSerializer(serializers.ModelSerializer):
    """Serializer for no-show alerts in Barber Dashboard"""
    customer_name = serializers.CharField(source='user.name', read_only=True)
    customer_email = serializers.EmailField(source='user.email', read_only=True)
    customer_phone = serializers.CharField(source='user.mobile_number', read_only=True)
    service_name = serializers.CharField(source='slot.service.title', read_only=True)
    scheduled_date = serializers.SerializerMethodField()
    scheduled_time = serializers.SerializerMethodField()
    
    class Meta:
        model = Booking
        fields = [
            'id',
            'customer_name',
            'customer_email',
            'customer_phone',
            'service_name',
            'scheduled_date',
            'scheduled_time',
            'created_at'
        ]
    
    def get_scheduled_date(self, obj):
        """Extract date from slot start_time"""
        if obj.slot and obj.slot.start_time:
            return obj.slot.start_time.date().isoformat()
        return None
    
    def get_scheduled_time(self, obj):
        """Extract time from slot start_time"""
        if obj.slot and obj.slot.start_time:
            return obj.slot.start_time.strftime('%H:%M:%S')
        return None


# ==========================================
# WALK-IN QUEUE SERIALIZERS
# ==========================================
from .models import WalkInEntry, LoyaltyProgram, LoyaltyPoints

class WalkInEntrySerializer(serializers.ModelSerializer):
    """Serializer for walk-in queue entries"""
    service_name = serializers.CharField(source='service.title', read_only=True)
    user_name = serializers.CharField(source='user.name', read_only=True)
    wait_time_display = serializers.SerializerMethodField()
    
    class Meta:
        model = WalkInEntry
        fields = [
            'id', 'shop', 'customer_name', 'customer_phone', 'customer_email',
            'user', 'user_name', 'service', 'service_name',
            'position', 'estimated_wait_minutes', 'wait_time_display',
            'status', 'notes',
            'joined_at', 'called_at', 'completed_at'
        ]
        read_only_fields = ['id', 'shop', 'joined_at', 'called_at', 'completed_at']
    
    def get_wait_time_display(self, obj):
        """Human readable wait time"""
        mins = obj.estimated_wait_minutes
        if mins < 60:
            return f"{mins} min"
        hours = mins // 60
        remaining = mins % 60
        return f"{hours}h {remaining}m"


# ==========================================
# LOYALTY PROGRAM SERIALIZERS
# ==========================================

class LoyaltyProgramSerializer(serializers.ModelSerializer):
    """Serializer for shop loyalty program settings"""
    
    class Meta:
        model = LoyaltyProgram
        fields = [
            'id', 'shop', 'is_active',
            'points_per_dollar', 'points_for_redemption',
            'reward_type', 'reward_value',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'shop', 'created_at', 'updated_at']


class LoyaltyPointsSerializer(serializers.ModelSerializer):
    """Serializer for customer loyalty points"""
    user_name = serializers.CharField(source='user.name', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    can_redeem = serializers.SerializerMethodField()
    
    class Meta:
        model = LoyaltyPoints
        fields = [
            'id', 'shop', 'user', 'user_name', 'user_email',
            'points_balance', 'total_points_earned', 'total_points_redeemed',
            'can_redeem', 'last_earned_at', 'last_redeemed_at'
        ]
        read_only_fields = ['id', 'shop', 'user', 'total_points_earned', 'total_points_redeemed']
    
    def get_can_redeem(self, obj):
        """Check if customer can redeem points"""
        try:
            program = obj.shop.loyalty_program
            return obj.points_balance >= program.points_for_redemption
        except LoyaltyProgram.DoesNotExist:
            return False
