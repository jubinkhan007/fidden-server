# api/walk_in_serializers.py
"""
Serializers for Walk-In Queue feature.
"""
from rest_framework import serializers
from .models import WalkInEntry, Service


class WalkInEntrySerializer(serializers.ModelSerializer):
    """Serializer for walk-in queue entries."""
    
    service_name = serializers.CharField(source='service.title', read_only=True)
    service_price = serializers.SerializerMethodField()
    wait_time_minutes = serializers.SerializerMethodField()
    
    class Meta:
        model = WalkInEntry
        fields = [
            'id', 'shop', 'service', 'service_name', 'service_price',
            'customer_name', 'customer_phone', 'customer_email',
            'user', 'position', 'estimated_wait_minutes', 'status', 
            'wait_time_minutes', 'notes',
            'joined_at', 'called_at', 'completed_at',
            'slot_booking', 'amount_paid', 'tips_amount', 'payment_method',
            'service_niche',
        ]
        read_only_fields = [
            'shop', 'position', 'joined_at', 'slot_booking'
        ]
    
    def get_service_price(self, obj):
        """Get service price (discount or regular)."""
        if obj.service:
            return obj.service.discount_price or obj.service.price
        return None
    
    def get_wait_time_minutes(self, obj):
        """Calculate wait time since check-in."""
        if obj.status != 'waiting':
            return 0
        from django.utils import timezone
        delta = timezone.now() - obj.joined_at
        return int(delta.total_seconds() / 60)
    
    def create(self, validated_data):
        request = self.context.get('request')
        shop = request.user.shop
        
        # Auto-assign queue position
        validated_data['shop'] = shop
        validated_data['position'] = WalkInEntry.get_next_queue_number(shop)
        
        # Auto-set service_niche from service category
        service = validated_data.get('service')
        if service and service.category:
            validated_data['service_niche'] = self._get_niche_from_category(service.category.name)
        
        return super().create(validated_data)
    
    def _get_niche_from_category(self, category_name):
        """Map category name to niche."""
        category_lower = category_name.lower()
        mapping = {
            'hair': 'hairstylist',
            'haircut': 'hairstylist',
            'hairstyle': 'hairstylist',
            'nails': 'nail_tech',
            'nail': 'nail_tech',
            'skincare': 'esthetician',
            'massage': 'massage_therapist',
            'tattoo': 'tattoo_artist',
            'makeup': 'makeup_artist',
            'barber': 'barber',
        }
        for key, niche in mapping.items():
            if key in category_lower:
                return niche
        return 'general'


class WalkInCheckoutSerializer(serializers.Serializer):
    """Serializer for completing a walk-in with payment."""
    
    payment_method = serializers.ChoiceField(
        choices=['cash', 'card', 'other'],
        required=True
    )
    amount_paid = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2,
        required=True
    )
    tips_amount = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2,
        default=0
    )


class WalkInStatsSerializer(serializers.Serializer):
    """Serializer for walk-in queue stats."""
    
    waiting = serializers.IntegerField()
    in_service = serializers.IntegerField()
    completed = serializers.IntegerField()
    no_show = serializers.IntegerField()
    total = serializers.IntegerField()
