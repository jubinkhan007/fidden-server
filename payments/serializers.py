from rest_framework import serializers
from stripe import Source
from .models import Payment, Booking
from django.db.models import Avg, Count

class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ['id', 'booking', 'user', 'amount', 'currency', 'status', 'stripe_payment_intent_id']
        read_only_fields = ['id', 'status', 'stripe_payment_intent_id', 'created_at', 'updated_at']

class userBookingSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    shop_name = serializers.CharField(source='shop.name', read_only=True)
    shop_address = serializers.CharField(source='shop.address', read_only=True)
    shop_img = serializers.SerializerMethodField()  # ✅ custom field for absolute URL
    slot_time = serializers.DateTimeField(source='slot.start_time', read_only=True)
    service_title = serializers.CharField(source='slot.service.title', read_only=True)
    service_duration = serializers.CharField(source='slot.service.duration', read_only=True)

    avg_rating = serializers.SerializerMethodField()
    total_reviews = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            'id',
            'user',
            'user_email',
            'shop',
            'shop_name',
            'shop_address',
            'shop_img',          
            'slot',
            'slot_time',
            'service_title',
            'service_duration',
            'status',
            'created_at',
            'updated_at',
            'avg_rating',
            'total_reviews',
        ]
        read_only_fields = fields

    def get_shop_img(self, obj):
        request = self.context.get("request")  # ✅ need request from view
        if obj.shop.shop_img:
            return request.build_absolute_uri(obj.shop.shop_img.url) if request else obj.shop.shop_img.url
        return None

    def get_avg_rating(self, obj):
        avg = obj.shop.ratings.aggregate(avg=Avg("rating"))["avg"]
        return round(avg, 1) if avg else 0

    def get_total_reviews(self, obj):
        return obj.shop.ratings.count()


class ownerBookingSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_name = serializers.CharField(source='user.name', read_only=True)
    profile_image = serializers.SerializerMethodField()   
    shop_name = serializers.CharField(source='shop.name', read_only=True)
    slot_time = serializers.DateTimeField(source='slot.start_time', read_only=True)
    service_title = serializers.CharField(source='slot.service.title', read_only=True)
    service_duration = serializers.CharField(source='slot.service.duration', read_only=True) 

    class Meta:
        model = Booking
        fields = [
            'id',
            'user',
            'user_email',
            'user_name',
            'profile_image',   
            'shop',
            'shop_name',
            'slot',
            'slot_time',
            'service_title',
            'service_duration',   
            'status',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_profile_image(self, obj):
        request = self.context.get("request")
        if obj.user.profile_image:
            return request.build_absolute_uri(obj.user.profile_image.url) if request else obj.user.profile_image.url
        return None