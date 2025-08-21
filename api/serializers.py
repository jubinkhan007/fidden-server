from rest_framework import serializers
from .models import Shop, Service, ServiceCategory


class ServiceCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceCategory
        fields = ['id', 'name']


class ServiceSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    category = serializers.PrimaryKeyRelatedField(queryset=ServiceCategory.objects.all())

    class Meta:
        model = Service
        fields = [
            'id', 'title', 'price', 'discount_price', 'description',
            'service_img', 'category', 'duration', 'capacity', 'is_active'
        ]
        read_only_fields = ('shop',)


class ShopSerializer(serializers.ModelSerializer):
    # ✅ removed services from response
    owner_id = serializers.IntegerField(source='owner.id', read_only=True)

    class Meta:
        model = Shop
        fields = [
            'id', 'name', 'address', 'location', 'capacity', 'start_at',
            'close_at', 'about_us', 'shop_img', 'close_days', 'owner_id'
        ]
        read_only_fields = ('owner_id',)

    def create(self, validated_data):
        shop = Shop.objects.create(**validated_data)
        return shop

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance
