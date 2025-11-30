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
    scheduled_date = serializers.DateField(source='slot.start_time', read_only=True)
    scheduled_time = serializers.TimeField(source='slot.start_time', read_only=True)
    
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
