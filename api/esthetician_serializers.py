# Esthetician/Massage Therapist Dashboard Serializers
from rest_framework import serializers
from .models import ClientSkinProfile, HealthDisclosure, TreatmentNote, RetailProduct


class ClientSkinProfileSerializer(serializers.ModelSerializer):
    """Serializer for client skin profiles with regimen"""
    client_name = serializers.CharField(source='client.name', read_only=True)
    client_email = serializers.EmailField(source='client.email', read_only=True)
    skin_type_display = serializers.CharField(source='get_skin_type_display', read_only=True)
    
    class Meta:
        model = ClientSkinProfile
        fields = [
            'id', 'shop', 'client', 'client_name', 'client_email',
            'skin_type', 'skin_type_display', 'primary_concerns',
            'allergies', 'sensitivities', 'current_products',
            'morning_routine', 'evening_routine', 'weekly_treatments',
            'regimen_notes', 'notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'shop', 'created_at', 'updated_at']


class HealthDisclosureSerializer(serializers.ModelSerializer):
    """Serializer for health disclosures"""
    client_name = serializers.CharField(source='client.name', read_only=True)
    client_email = serializers.EmailField(source='client.email', read_only=True)
    pressure_display = serializers.CharField(source='get_pressure_preference_display', read_only=True)
    
    class Meta:
        model = HealthDisclosure
        fields = [
            'id', 'shop', 'client', 'client_name', 'client_email', 'booking',
            'has_medical_conditions', 'conditions_detail',
            'current_medications', 'allergies',
            'pregnant_or_nursing', 'recent_surgeries',
            'pressure_preference', 'pressure_display',
            'areas_to_avoid', 'areas_to_focus',
            'acknowledged', 'acknowledged_at', 'created_by',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'shop', 'created_at', 'updated_at']


class TreatmentNoteSerializer(serializers.ModelSerializer):
    """Serializer for treatment notes"""
    client_name = serializers.CharField(source='client.name', read_only=True)
    treatment_type_display = serializers.CharField(source='get_treatment_type_display', read_only=True)
    booking_date = serializers.DateTimeField(source='booking.slot.start_time', read_only=True)
    service_title = serializers.CharField(source='booking.slot.service.title', read_only=True)
    
    class Meta:
        model = TreatmentNote
        fields = [
            'id', 'shop', 'client', 'client_name', 'booking',
            'booking_date', 'service_title',
            'treatment_type', 'treatment_type_display',
            'products_used', 'observations',
            'recommendations', 'next_appointment_notes',
            'before_photo_url', 'after_photo_url',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'shop', 'created_at', 'updated_at']


class RetailProductSerializer(serializers.ModelSerializer):
    """Serializer for retail products"""
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    
    class Meta:
        model = RetailProduct
        fields = [
            'id', 'shop', 'name', 'brand',
            'category', 'category_display',
            'price', 'description', 'image_url',
            'in_stock', 'purchase_link', 'is_active',
            'created_at'
        ]
        read_only_fields = ['id', 'shop', 'created_at']


class EstheticianDashboardSerializer(serializers.Serializer):
    """Aggregated dashboard data for Esthetician"""
    today_appointments_count = serializers.IntegerField()
    week_appointments_count = serializers.IntegerField()
    today_revenue = serializers.DecimalField(max_digits=10, decimal_places=2)
    client_profiles_count = serializers.IntegerField()
    retail_products_count = serializers.IntegerField()
    disclosure_alerts = serializers.ListField()
    recent_treatment_notes = serializers.ListField()
