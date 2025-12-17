# Makeup Artist Dashboard Serializers
from rest_framework import serializers
from .models import ClientBeautyProfile, ProductKitItem, GalleryItem


class ClientBeautyProfileSerializer(serializers.ModelSerializer):
    """Serializer for client beauty profiles"""
    client_name = serializers.CharField(source='client.name', read_only=True)
    client_email = serializers.EmailField(source='client.email', read_only=True)
    skin_tone_display = serializers.CharField(source='get_skin_tone_display', read_only=True)
    skin_type_display = serializers.CharField(source='get_skin_type_display', read_only=True)
    undertone_display = serializers.CharField(source='get_undertone_display', read_only=True)
    
    class Meta:
        model = ClientBeautyProfile
        fields = [
            'id', 'shop', 'client', 'client_name', 'client_email',
            'skin_tone', 'skin_tone_display',
            'skin_type', 'skin_type_display',
            'undertone', 'undertone_display',
            'allergies', 'preferences', 'foundation_shade',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'shop', 'created_at', 'updated_at']


class ProductKitItemSerializer(serializers.ModelSerializer):
    """Serializer for product kit items"""
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    
    class Meta:
        model = ProductKitItem
        fields = [
            'id', 'shop', 'name', 'brand',
            'category', 'category_display',
            'quantity', 'is_packed', 'notes',
            'created_at'
        ]
        read_only_fields = ['id', 'shop', 'created_at']


class FaceChartSerializer(serializers.ModelSerializer):
    """Serializer for face charts (GalleryItem with client link)"""
    client_name = serializers.CharField(source='client.name', read_only=True)
    
    class Meta:
        model = GalleryItem
        fields = [
            'id', 'shop', 'image', 'thumbnail', 'caption', 'description',
            'client', 'client_name', 'look_type',
            'category_tag', 'tags', 'is_public',
            'created_at'
        ]
        read_only_fields = ['id', 'shop', 'thumbnail', 'created_at']


class MUADashboardSerializer(serializers.Serializer):
    """Aggregated dashboard data for MUA"""
    today_appointments_count = serializers.IntegerField()
    today_revenue = serializers.DecimalField(max_digits=10, decimal_places=2)
    client_profiles_count = serializers.IntegerField()
    product_kit_count = serializers.IntegerField()
    face_charts_count = serializers.IntegerField()
    mobile_services_count = serializers.IntegerField()
