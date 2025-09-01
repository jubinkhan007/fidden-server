from rest_framework import serializers
from .models import (
    Shop, 
    Service, 
    ServiceCategory, 
    RatingReview, 
    Slot, 
    SlotBooking, 
    FavoriteShop,
    Promotion,
    ServiceWishlist
)
from math import radians, cos, sin, asin, sqrt
from django.db.models.functions import Coalesce
from django.db.models import Avg, Count, Q, Value, FloatField


class ServiceCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceCategory
        fields = ['id', 'name', 'sc_img']

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        request = self.context.get('request')
        
        if instance.sc_img and instance.sc_img.name:
            if request:
                rep['sc_img'] = request.build_absolute_uri(instance.sc_img.url)
            else:
                # fallback if request not available
                rep['sc_img'] = instance.sc_img.url
        else:
            rep['sc_img'] = None

        return rep


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


class SlotSerializer(serializers.ModelSerializer):
    available = serializers.SerializerMethodField()

    class Meta:
        model = Slot
        fields = ['id', 'shop', 'service', 'start_time', 'end_time', 'capacity_left', 'available']

    def get_available(self, obj):
        # Service-level capacity check
        service_capacity_ok = obj.capacity_left > 0

        # Shop-level capacity check
        shop_capacity_ok = obj.service.shop.capacity > 0

        return service_capacity_ok and shop_capacity_ok


class SlotBookingSerializer(serializers.ModelSerializer):
    slot_id = serializers.PrimaryKeyRelatedField(
        queryset=Slot.objects.all(),
        write_only=True,
        source='slot'  # maps slot_id to slot internally
    )

    class Meta:
        model = SlotBooking
        fields = ['id', 'slot_id', 'user', 'shop', 'service', 'start_time', 'end_time', 'status', 'created_at']
        read_only_fields = ['user', 'shop', 'service', 'start_time', 'end_time', 'status', 'created_at']

    def create(self, validated_data):
        user = self.context['request'].user
        slot = validated_data.pop('slot')

        # Check overlapping bookings
        from django.db.models import Q
        if SlotBooking.objects.filter(
            user=user,
            status="confirmed"
        ).filter(
            Q(start_time__lt=slot.end_time) & Q(end_time__gt=slot.start_time)
        ).exists():
            raise serializers.ValidationError("You already have a booking that overlaps this slot.")

        # Check slot capacity
        if slot.capacity_left <= 0:
            raise serializers.ValidationError("This slot is fully booked.")

        booking = SlotBooking.objects.create(
            user=user,
            slot=slot,
            start_time=slot.start_time,
            end_time=slot.end_time,
            shop=slot.shop,
            service=slot.service,
            status='confirmed'
        )

        # Reduce slot capacity
        slot.capacity_left -= 1
        slot.save(update_fields=['capacity_left'])

        return booking

class ShopListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    address = serializers.CharField()
    location = serializers.CharField(allow_null=True)
    avg_rating = serializers.FloatField()
    review_count = serializers.IntegerField()
    distance = serializers.SerializerMethodField()
    shop_img = serializers.SerializerMethodField()
    badge = serializers.SerializerMethodField()  # Added badge as method field

    def get_shop_img(self, obj):
        request = self.context.get("request")
        if obj.shop_img and obj.shop_img.name and obj.shop_img.storage.exists(obj.shop_img.name):
            return request.build_absolute_uri(obj.shop_img.url)
        return None

    def get_distance(self, obj):
        """
        Calculate distance from user's location passed in context:
        context = {"user_location": "lon,lat"}  (optional)
        """
        user_location = self.context.get("user_location")
        if not user_location or not obj.location:
            return None
        try:
            user_lon, user_lat = map(float, user_location.split(","))
            shop_lon, shop_lat = map(float, obj.location.split(","))
        except Exception:
            return None

        # Haversine formula
        lon1, lat1, lon2, lat2 = map(radians, [user_lon, user_lat, shop_lon, shop_lat])
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))
        km = 6371 * c
        return round(km * 1000, 2)  # meters

    def get_badge(self, obj):
        return "Top"
    
class ShopDetailSerializer(serializers.ModelSerializer):
    owner_id = serializers.IntegerField(source='owner.id', read_only=True)
    avg_rating = serializers.FloatField(read_only=True)
    review_count = serializers.IntegerField(read_only=True)
    distance = serializers.FloatField(read_only=True)  # in meters
    services = serializers.SerializerMethodField()
    reviews = serializers.SerializerMethodField()

    class Meta:
        model = Shop
        fields = [
            'id', 'name', 'address', 'location', 'capacity', 'start_at',
            'close_at', 'about_us', 'shop_img', 'close_days', 'owner_id',
            'avg_rating', 'review_count', 'distance', 'services', 'reviews'
        ]

    def get_services(self, obj):
        services = obj.services.filter(is_active=True)
        request = self.context.get('request')
        return [
            {
                'id': s.id,
                'title': s.title,
                'description': s.description,
                'price': s.price,
                'discount_price': s.discount_price,
                'service_img': (
                    request.build_absolute_uri(s.service_img.url)
                    if s.service_img and request else s.service_img.url if s.service_img else None
                )
            }
            for s in services
        ]

    def get_reviews(self, obj):
        reviews = obj.ratings.all().order_by('-created_at')
        request = self.context.get('request')
        return [
            {
                'id': r.id,
                'service': r.service.id,
                'user': r.user.id if r.user else None,
                'user_name': r.user.name if r.user and r.user.name else "Anonymous",
                'profile_image': (
                    request.build_absolute_uri(r.user.profile_image.url)
                    if getattr(r.user, 'profile_image', None) and request else None
                ),
                'rating': r.rating,
                'review': r.review,
                'review_img': (
                    request.build_absolute_uri(r.review_img.url)
                    if r.review_img and request else r.review_img.url if r.review_img else None
                ),
                'created_at': r.created_at
            }
            for r in reviews
        ]

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        request = self.context.get('request')
        rep['shop_img'] = (
            request.build_absolute_uri(instance.shop_img.url)
            if instance.shop_img and request else instance.shop_img.url if instance.shop_img else None
        )
        # Round avg_rating to 1 decimal
        if 'avg_rating' in rep and rep['avg_rating'] is not None:
            rep['avg_rating'] = round(rep['avg_rating'], 1)
        return rep

class ServiceListSerializer(serializers.ModelSerializer):
    shop_id = serializers.IntegerField(source="shop.id", read_only=True)
    shop_address = serializers.CharField(source="shop.address", read_only=True)
    avg_rating = serializers.FloatField(read_only=True)
    review_count = serializers.IntegerField(read_only=True)
    badge = serializers.SerializerMethodField()
    distance = serializers.SerializerMethodField()  # <-- added distance

    class Meta:
        model = Service
        fields = [
            "id",
            "title",
            "price",
            "discount_price",
            "category",
            "shop_id",
            "shop_address",
            "avg_rating",
            "review_count",
            "service_img",
            "badge",
            "distance",  # <-- added distance
            "is_active" 
        ]
    
    def get_badge(self, obj):
        return "Trending"

    def get_distance(self, obj):
        """
        Calculate distance from user's location passed in context:
        context = {"user_location": "lon,lat"}  (optional)
        """
        user_location = self.context.get("user_location")
        shop_location = getattr(obj.shop, "location", None)
        if not user_location or not shop_location:
            return None
        try:
            user_lon, user_lat = map(float, user_location.split(","))
            shop_lon, shop_lat = map(float, shop_location.split(","))
        except Exception:
            return None

        # Haversine formula
        lon1, lat1, lon2, lat2 = map(radians, [user_lon, user_lat, shop_lon, shop_lat])
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))
        km = 6371 * c
        return round(km * 1000, 2)  # meters

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        request = self.context.get("request")
        rep["service_img"] = (
            request.build_absolute_uri(instance.service_img.url)
            if instance.service_img and request
            else instance.service_img.url if instance.service_img else None
        )
        if rep.get("avg_rating") is not None:
            rep["avg_rating"] = round(rep["avg_rating"], 1)
        return rep

class ServiceDetailSerializer(serializers.ModelSerializer):
    shop_id = serializers.IntegerField(source="shop.id", read_only=True)
    shop_name = serializers.CharField(source="shop.name", read_only=True)
    avg_rating = serializers.FloatField(read_only=True)
    review_count = serializers.IntegerField(read_only=True)
    reviews = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = [
            "id",
            "service_img",
            "title",
            "price",
            "discount_price",
            "description",
            "duration",
            "shop_id",
            "shop_name",
            "avg_rating",
            "review_count",
            "reviews",
        ]

    def get_reviews(self, obj):
        request = self.context.get("request")
        # Sort by rating descending first, then latest created
        reviews = (
            RatingReview.objects.filter(service=obj)
            .select_related("user", "shop")
            .order_by("-rating", "-created_at")
        )
        return RatingReviewSerializer(reviews, many=True, context={"request": request}).data

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        request = self.context.get("request")
        rep["service_img"] = (
            request.build_absolute_uri(instance.service_img.url)
            if instance.service_img and request else instance.service_img.url if instance.service_img else None
        )
        if rep.get("avg_rating") is not None:
            rep["avg_rating"] = round(rep["avg_rating"], 1)
        return rep

class FavoriteShopSerializer(serializers.ModelSerializer):
    shop_id = serializers.IntegerField(write_only=True, required=False)
    name = serializers.CharField(source='shop.name', read_only=True)
    address = serializers.CharField(source='shop.address', read_only=True)
    location = serializers.CharField(source='shop.location', read_only=True)
    avg_rating = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()
    distance = serializers.SerializerMethodField()

    class Meta:
        model = FavoriteShop
        fields = ['id', 'shop_id', 'name', 'address', 'location', 'avg_rating', 'review_count', 'distance', 'created_at']

    def validate_shop_id(self, value):
        if not Shop.objects.filter(id=value).exists():
            raise serializers.ValidationError("Shop does not exist.")
        return value

    def create(self, validated_data):
        user = self.context['request'].user
        shop = Shop.objects.get(id=validated_data['shop_id'])
        favorite, created = FavoriteShop.objects.get_or_create(user=user, shop=shop)
        return favorite

    def get_avg_rating(self, obj):
        return obj.shop.ratings.aggregate(avg=Coalesce(Avg('rating'), Value(0.0, output_field=FloatField())))['avg']

    def get_review_count(self, obj):
        return obj.shop.ratings.aggregate(
            count=Count('id', filter=Q(review__isnull=False) & ~Q(review__exact=''))
        )['count']

    def get_distance(self, obj):
        user_location = self.context.get('user_location')
        if not user_location or not obj.shop.location:
            return None
        try:
            user_lon, user_lat = map(float, user_location.split(','))
            shop_lon, shop_lat = map(float, obj.shop.location.split(','))
            lon1, lat1, lon2, lat2 = map(radians, [user_lon, user_lat, shop_lon, shop_lat])
            dlon = lon2 - lon1
            dlat = lat2 - lat1
            a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
            c = 2*asin(sqrt(a))
            km = 6371 * c
            return round(km*1000, 2)  # meters
        except:
            return None

class PromotionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Promotion
        fields = ['id', 'title', 'subtitle', 'amount', 'is_active', 'created_at']

class ServiceWishlistSerializer(serializers.ModelSerializer):
    # For POST: write-only input
    service_no = serializers.IntegerField(write_only=True, required=True)

    # For GET: read-only response (use service_id for the field name)
    service_id = serializers.IntegerField(source='service.id', read_only=True)
    title = serializers.CharField(source='service.title', read_only=True)
    price = serializers.DecimalField(source='service.price', max_digits=10, decimal_places=2, read_only=True)
    discount_price = serializers.DecimalField(source='service.discount_price', max_digits=10, decimal_places=2, read_only=True)
    category = serializers.CharField(source='service.category.id', read_only=True)
    shop_id = serializers.IntegerField(source='service.shop.id', read_only=True)
    shop_name = serializers.CharField(source='service.shop.name', read_only=True)
    shop_address = serializers.CharField(source='service.shop.address', read_only=True)
    avg_rating = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()
    badge = serializers.SerializerMethodField()
    service_img = serializers.SerializerMethodField()
    is_active = serializers.BooleanField(source='service.is_active', read_only=True)

    class Meta:
        model = ServiceWishlist
        fields = [
            'id', 'service_no', 'service_id', 'title', 'price', 'discount_price', 'category',
            'shop_id', 'shop_name', 'shop_address',
            'avg_rating', 'review_count', 'badge', 'service_img', 'is_active', 'created_at'
        ]

    def validate_service_no(self, value):
        if not Service.objects.filter(id=value, is_active=True).exists():
            raise serializers.ValidationError("Active service does not exist.")
        return value

    def create(self, validated_data):
        user = self.context['request'].user
        service = Service.objects.get(id=validated_data['service_no'], is_active=True)
        wishlist, created = ServiceWishlist.objects.get_or_create(user=user, service=service)
        return wishlist

    def get_avg_rating(self, obj):
        return obj.service.ratings.aggregate(avg=Coalesce(Avg('rating'), Value(0.0, output_field=FloatField())))['avg']

    def get_review_count(self, obj):
        return obj.service.ratings.aggregate(
            count=Count('id', filter=Q(review__isnull=False) & ~Q(review__exact=''))
        )['count']

    def get_badge(self, obj):
        avg_rating = self.get_avg_rating(obj)
        return "Top" if avg_rating and avg_rating >= 4.5 else None

    def get_service_img(self, obj):
        request = self.context.get('request')
        if obj.service.service_img and obj.service.service_img.name and obj.service.service_img.storage.exists(obj.service.service_img.name):
            return request.build_absolute_uri(obj.service.service_img.url) if request else obj.service.service_img.url
        return None

class GlobalSearchSerializer(serializers.Serializer):
    type = serializers.CharField()        # "shop" or "service"
    id = serializers.IntegerField()
    title = serializers.CharField()
    extra_info = serializers.CharField(allow_null=True, required=False)
    image = serializers.CharField(allow_null=True, required=False)

    distance = serializers.FloatField(allow_null=True, required=False)
    rating = serializers.FloatField(allow_null=True, required=False)
    relevance = serializers.FloatField(allow_null=True, required=False)