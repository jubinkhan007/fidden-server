# Nail Tech Dashboard Serializers
from rest_framework import serializers
from .models import StyleRequest, StyleRequestImage, Service, GalleryItem
from payments.models import Booking


class StyleRequestImageSerializer(serializers.ModelSerializer):
    """Serializer for style request reference images"""
    
    class Meta:
        model = StyleRequestImage
        fields = ['id', 'image', 'uploaded_at']
        read_only_fields = ['id', 'uploaded_at']


class StyleRequestSerializer(serializers.ModelSerializer):
    """Serializer for nail style requests"""
    user_name = serializers.CharField(source='user.name', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    images = StyleRequestImageSerializer(many=True, read_only=True)
    nail_style_type_display = serializers.CharField(
        source='get_nail_style_type_display', read_only=True
    )
    nail_shape_display = serializers.CharField(
        source='get_nail_shape_display', read_only=True
    )
    
    class Meta:
        model = StyleRequest
        fields = [
            'id', 'shop', 'user', 'user_name', 'user_email', 'booking',
            'title', 'description', 
            'nail_style_type', 'nail_style_type_display',
            'nail_shape', 'nail_shape_display',
            'color_preference', 'status', 'images',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'shop', 'created_at', 'updated_at']


class LookbookItemSerializer(serializers.ModelSerializer):
    """Serializer for nail lookbook/moodboard items (uses GalleryItem)"""
    
    class Meta:
        model = GalleryItem
        fields = [
            'id', 'image', 'thumbnail', 'caption', 
            'category_tag', 'is_public', 'created_at'
        ]


class BookingByStyleSerializer(serializers.Serializer):
    """Serializer for bookings grouped by style type"""
    style_type = serializers.CharField()
    style_display = serializers.CharField()
    count = serializers.IntegerField()
    revenue = serializers.DecimalField(max_digits=10, decimal_places=2)


class TipSummarySerializer(serializers.Serializer):
    """Serializer for tip summary"""
    period = serializers.CharField()
    total_tips = serializers.DecimalField(max_digits=10, decimal_places=2)
    tip_count = serializers.IntegerField()
    average_tip = serializers.DecimalField(max_digits=10, decimal_places=2)


class NailTechDashboardSerializer(serializers.Serializer):
    """Aggregated dashboard data for Nail Tech"""
    today_appointments_count = serializers.IntegerField()
    today_revenue = serializers.DecimalField(max_digits=10, decimal_places=2)
    pending_style_requests = serializers.IntegerField()
    repeat_customer_rate = serializers.FloatField()
    weekly_tips = serializers.DecimalField(max_digits=10, decimal_places=2)
    lookbook_count = serializers.IntegerField()
