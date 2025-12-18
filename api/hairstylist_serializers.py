# Hairstylist/Loctician Dashboard Serializers
from rest_framework import serializers
from .models import ClientHairProfile, ProductRecommendation
from payments.models import Booking


class ClientHairProfileSerializer(serializers.ModelSerializer):
    """Serializer for client hair profiles"""
    client_name = serializers.CharField(source='client.name', read_only=True)
    client_email = serializers.EmailField(source='client.email', read_only=True)
    hair_type_display = serializers.CharField(source='get_hair_type_display', read_only=True)
    hair_texture_display = serializers.CharField(source='get_hair_texture_display', read_only=True)
    hair_porosity_display = serializers.CharField(source='get_hair_porosity_display', read_only=True)
    
    class Meta:
        model = ClientHairProfile
        fields = [
            'id', 'shop', 'client', 'client_name', 'client_email',
            'hair_type', 'hair_type_display',
            'hair_texture', 'hair_texture_display',
            'hair_porosity', 'hair_porosity_display',
            'natural_color', 'current_color',
            'color_history', 'chemical_history',
            'scalp_condition', 'allergies', 'preferences',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'shop', 'created_at', 'updated_at']


class ProductRecommendationSerializer(serializers.ModelSerializer):
    """Serializer for product recommendations"""
    client_name = serializers.CharField(source='client.name', read_only=True)
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    
    class Meta:
        model = ProductRecommendation
        fields = [
            'id', 'shop', 'client', 'client_name', 'booking',
            'product_name', 'brand',
            'category', 'category_display',
            'notes', 'purchase_link',
            'created_at'
        ]
        read_only_fields = ['id', 'shop', 'created_at']


class PrepNotesSerializer(serializers.ModelSerializer):
    """Serializer for booking prep notes"""
    user_name = serializers.CharField(source='user.name', read_only=True)
    service_title = serializers.CharField(source='slot.service.title', read_only=True)
    slot_time = serializers.DateTimeField(source='slot.start_time', read_only=True)
    
    class Meta:
        model = Booking
        fields = [
            'id', 'user_name', 'service_title', 'slot_time',
            'prep_notes', 'status'
        ]
        read_only_fields = ['id', 'user_name', 'service_title', 'slot_time', 'status']


class HairstylistDashboardSerializer(serializers.Serializer):
    """Aggregated dashboard data for Hairstylist"""
    today_appointments_count = serializers.IntegerField()
    week_appointments_count = serializers.IntegerField()
    today_revenue = serializers.DecimalField(max_digits=10, decimal_places=2)
    client_profiles_count = serializers.IntegerField()
    product_recommendations_count = serializers.IntegerField()
    consultation_services_count = serializers.IntegerField()
