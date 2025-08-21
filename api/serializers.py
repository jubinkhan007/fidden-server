from rest_framework import serializers
from .models import Shop, Service, ServiceCategory, RatingReview


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

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        request = self.context.get('request')
        # Return full URL if request is available
        rep['service_img'] = (
            request.build_absolute_uri(instance.service_img.url)
            if instance.service_img and request else instance.service_img.url if instance.service_img else None
        )
        return rep


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

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        request = self.context.get('request')
        rep['shop_img'] = (
            request.build_absolute_uri(instance.shop_img.url)
            if instance.shop_img and request else instance.shop_img.url if instance.shop_img else None
        )
        return rep

    def create(self, validated_data):
        shop = Shop.objects.create(**validated_data)
        return shop

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance

class RatingReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = RatingReview
        fields = [
            'id', 'shop', 'service', 'user', 'user_name',
            'rating', 'review', 'review_img', 'created_at'
        ]
        read_only_fields = ['user', 'created_at', 'user_name']

    def get_user_name(self, obj):
        if obj.user:
            return obj.user.name  or "Anonymous"
        return "Anonymous"

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        request = self.context.get('request')
        rep['review_img'] = (
            request.build_absolute_uri(instance.review_img.url)
            if instance.review_img and request else instance.review_img.url if instance.review_img else None
        )
        return rep

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)