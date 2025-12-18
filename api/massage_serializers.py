# Massage Therapist Dashboard Serializers
from rest_framework import serializers
from .models import ClientMassageProfile, SessionNote, HealthDisclosure


class ClientMassageProfileSerializer(serializers.ModelSerializer):
    """Serializer for client massage profiles"""
    client_name = serializers.CharField(source='client.name', read_only=True)
    client_email = serializers.EmailField(source='client.email', read_only=True)
    pressure_display = serializers.CharField(source='get_pressure_preference_display', read_only=True)
    
    class Meta:
        model = ClientMassageProfile
        fields = [
            'id', 'shop', 'client', 'client_name', 'client_email',
            'pressure_preference', 'pressure_display',
            'areas_to_focus', 'areas_to_avoid',
            'has_injuries', 'injury_details',
            'has_chronic_conditions', 'chronic_conditions',
            'preferred_techniques', 'temperature_preference',
            'music_preference', 'aromatherapy_preference',
            'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'shop', 'created_at', 'updated_at']


class SessionNoteSerializer(serializers.ModelSerializer):
    """Serializer for session notes"""
    client_name = serializers.CharField(source='client.name', read_only=True)
    technique_display = serializers.CharField(source='get_technique_used_display', read_only=True)
    booking_date = serializers.DateTimeField(source='booking.slot.start_time', read_only=True)
    service_title = serializers.CharField(source='booking.slot.service.title', read_only=True)
    
    class Meta:
        model = SessionNote
        fields = [
            'id', 'shop', 'client', 'client_name', 'booking',
            'booking_date', 'service_title',
            'technique_used', 'technique_display',
            'pressure_applied', 'areas_worked',
            'tension_observations', 'recommendations',
            'next_session_notes', 'duration_minutes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'shop', 'created_at', 'updated_at']


class MassageHealthDisclosureSerializer(serializers.ModelSerializer):
    """Health disclosure serializer focused on massage-specific fields"""
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
            'acknowledged', 'acknowledged_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'shop', 'created_at', 'updated_at']


class MassageDashboardSerializer(serializers.Serializer):
    """Aggregated dashboard data for Massage Therapist"""
    today_appointments_count = serializers.IntegerField()
    week_appointments_count = serializers.IntegerField()
    today_revenue = serializers.DecimalField(max_digits=10, decimal_places=2)
    client_profiles_count = serializers.IntegerField()
    disclosure_alerts = serializers.ListField()
    recent_session_notes = serializers.ListField()
