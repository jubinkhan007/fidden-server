# Barber Dashboard Serializers
from rest_framework import serializers
from payments.models import Booking

class BarberAppointmentSerializer(serializers.ModelSerializer):
    """Serializer for today's appointments in Barber Dashboard"""
    customer_name = serializers.CharField(source='user.name', read_only=True)
    customer_email = serializers.EmailField(source='user.email', read_only=True)
    service_name = serializers.CharField(source='slot.service.title', read_only=True)
    service_duration = serializers.IntegerField(source='slot.service.duration', read_only=True)
    start_time = serializers.DateTimeField(source='slot.start_time', read_only=True)
    end_time = serializers.DateTimeField(source='slot.end_time', read_only=True)
    
    class Meta:
        model = Booking
        fields = [
            'id',
            'customer_name',
            'customer_email',
            'service_name',
            'service_duration',
            'start_time',
            'end_time',
            'status',
            'created_at'
        ]


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
