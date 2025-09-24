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
    ServiceWishlist,
    VerificationFile,
    Reply,
    ChatThread, 
    Message, 
    Notification,
    Device,
    Revenue,
    Coupon
)
from math import radians, cos, sin, asin, sqrt
from django.db.models.functions import Coalesce
from django.db.models import Avg, Count, Q, Value, FloatField
from api.utils.helper_function import get_distance
from django.db import transaction
from django.utils import timezone


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

class VerificationFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = VerificationFile
        fields = ["id", "file", "uploaded_at"]

class ShopSerializer(serializers.ModelSerializer):
    # ✅ removed services from response
    owner_id = serializers.IntegerField(source='owner.id', read_only=True)
    # 👇 for multiple file uploads at creation
    verification_files = serializers.ListField(
        child=serializers.FileField(),
        write_only=True,
        required=True  # 🔥 mandatory
    )
    uploaded_files = VerificationFileSerializer(source="verification_files", many=True, read_only=True)

    class Meta:
        model = Shop
        fields = [
            'id', 'name', 'address', 'location', 'capacity', 'start_at',
            'close_at', 'about_us', 'shop_img', 'close_days', 'owner_id', 
            'is_verified', 'status', 'verification_files', 'uploaded_files'
        ]
        read_only_fields = ('owner_id','is_verified', 'uploaded_files')

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        request = self.context.get('request')
        rep['shop_img'] = (
            request.build_absolute_uri(instance.shop_img.url)
            if instance.shop_img and request else instance.shop_img.url if instance.shop_img else None
        )
        return rep

    def create(self, validated_data):
        files = validated_data.pop("verification_files", None)

        if not files:
            raise serializers.ValidationError(
                {"verification_files": "At least one verification file is required."}
            )

        shop = Shop.objects.create(**validated_data)

        for f in files:
            VerificationFile.objects.create(shop=shop, file=f)

        return shop

    def update(self, instance, validated_data):
        # Reset status to pending on update
        instance.status = "pending"

        # ⚡ optional: allow uploading new verification files during update
        files = validated_data.pop("verification_files", None)  

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if files:
            for f in files:
                VerificationFile.objects.create(shop=instance, file=f)

        return instance

class ReplySerializer(serializers.ModelSerializer):
    
    class Meta:
        model = Reply
        fields = ['id', 'message', 'created_at']

class RatingReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField(read_only=True)
    reply = ReplySerializer(source='replies', many=True, read_only=True)
    booking_id = serializers.IntegerField(write_only=True, required=True)

    class Meta:
        model = RatingReview
        fields = [
            'id', 'shop', 'service', 'user', 'user_name',
            'booking_id', 'rating', 'review', 'review_img', 'reply', 'created_at'
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
        # show booking id in response
        rep['booking_id'] = instance.booking.id if instance.booking else None
        return rep

    def create(self, validated_data):
        booking_id = validated_data.pop("booking_id")
        request = self.context['request']
        validated_data['user'] = request.user

        from payments.models import Booking
        try:
            booking = Booking.objects.get(id=booking_id)
        except Booking.DoesNotExist:
            raise serializers.ValidationError({"detail": "Invalid booking_id"})

        # prevent duplicate review for same booking
        if hasattr(booking, "review"):
            raise serializers.ValidationError({"detail": "You have already submitted a review for this booking."})

        validated_data["booking"] = booking
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

    def validate(self, attrs):
        """Additional validation before creation"""
        slot = attrs.get('slot')
        user = self.context['request'].user
        
        # Check slot capacity in validation phase
        if slot.capacity_left <= 0:
            raise serializers.ValidationError("This slot is fully booked.")
        
        # Check for overlapping bookings
        overlapping = SlotBooking.objects.filter(
            user=user,
            status="confirmed"
        ).filter(
            Q(start_time__lt=slot.end_time) & Q(end_time__gt=slot.start_time)
        )
        
        if overlapping.exists():
            raise serializers.ValidationError("You already have a booking that overlaps this slot.")
        
        return attrs

    def create(self, validated_data):
        user = self.context['request'].user
        slot = validated_data.pop('slot')

        # Use atomic transaction with locking to prevent race conditions
        with transaction.atomic():
            # Lock the slot row to prevent concurrent bookings
            slot = Slot.objects.select_for_update().get(id=slot.id)
            
            # Double-check capacity after locking (race condition protection)
            if slot.capacity_left <= 0:
                raise serializers.ValidationError("This slot is fully booked.")
            
            # Double-check overlapping bookings after locking
            overlapping = SlotBooking.objects.filter(
                user=user,
                status="confirmed"
            ).filter(
                Q(start_time__lt=slot.end_time) & Q(end_time__gt=slot.start_time)
            )
            
            if overlapping.exists():
                raise serializers.ValidationError("You already have a booking that overlaps this slot.")

            # Create the booking
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
        user_location = self.context.get("user_location")
        return get_distance(user_location, obj.location)

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
        request = self.context.get('request')
        category_id = self.context.get('category_id')  # optional filter

        services = obj.services.filter(is_active=True)
        if category_id:
            try:
                category_id = int(category_id)
                services = services.filter(category=category_id)  # <- use `category` here
            except ValueError:
                pass

        return [
            {
                'id': s.id,
                'title': s.title,
                'description': s.description,
                'price': s.price,
                'discount_price': s.discount_price,
                'category_id': s.category.id if s.category else None,
                'category_name': s.category.name if s.category else None,
                'category_img': (
                    request.build_absolute_uri(s.category.sc_img.url)
                    if s.category and s.category.sc_img and request else s.category.sc_img.url if s.category and s.category.sc_img else None
                ),
                'service_img': (
                    request.build_absolute_uri(s.service_img.url)
                    if s.service_img and request else s.service_img.url if s.service_img else None
                )
            }
            for s in services
        ]

    def get_reviews(self, obj):
        # Prefetch replies, service, and user to avoid N+1 queries
        reviews = obj.ratings.all().prefetch_related(
            'replies',      # Prefetch replies
            'service',      # Prefetch service for each review
            'user'          # Prefetch user for each review
        ).order_by('-created_at')
        
        request = self.context.get('request')
        review_list = []
        
        for review in reviews:
            # Process replies for this review - only include id, message, and created_at
            replies = []
            for reply in review.replies.all():
                replies.append({
                    'id': reply.id,
                    'message': reply.message,
                    'created_at': reply.created_at
                })
            
            # Build review data
            review_data = {
                'id': review.id,
                'service_id': review.service.id if review.service else None,
                'service_name': review.service.title if review.service else None,
                'user_id': review.user.id if review.user else None,
                'user_name': review.user.name if review.user and review.user.name else "Anonymous",
                'rating': review.rating,
                'review': review.review,
                'created_at': review.created_at,
                'replies': replies  # Include the simplified replies array
            }
            
            # Add user image
            if review.user and getattr(review.user, 'profile_image', None):
                review_data['user_img'] = (
                    request.build_absolute_uri(review.user.profile_image.url)
                    if request else review.user.profile_image.url
                )
            else:
                review_data['user_img'] = None
            
            # Add review image
            if review.review_img:
                review_data['review_img'] = (
                    request.build_absolute_uri(review.review_img.url)
                    if request else review.review_img.url
                )
            else:
                review_data['review_img'] = None
            
            review_list.append(review_data)
        
        return review_list

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
        user_location = self.context.get("user_location")
        return get_distance(user_location, obj.shop.location if obj.shop else None)

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
    shop_address = serializers.CharField(source="shop.address", read_only=True)
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
            "shop_address",
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
    shop_no = serializers.IntegerField(source='shop.id', read_only=True) 
    name = serializers.CharField(source='shop.name', read_only=True)
    address = serializers.CharField(source='shop.address', read_only=True)
    location = serializers.CharField(source='shop.location', read_only=True)
    avg_rating = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()
    distance = serializers.SerializerMethodField()

    class Meta:
        model = FavoriteShop
        fields = ['id', 'shop_id', 'shop_no', 'name', 'address', 'location', 'avg_rating', 'review_count', 'distance', 'created_at']

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
        user_location = self.context.get("user_location")
        return get_distance(user_location, obj.shop.location if obj.shop else None)

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

class ReplyCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating replies to rating reviews
    """
    class Meta:
        model = Reply
        fields = ['message']

    def validate_message(self, value):
        """
        Validate the message field
        """
        if not value.strip():
            raise serializers.ValidationError("Message cannot be empty.")
        return value

    def create(self, validated_data):
        """
        Create and return a new Reply instance
        """
        # Get context from view
        rating_review = self.context.get('rating_review')
        user = self.context.get('request').user
        
        # Create the reply
        reply = Reply.objects.create(
            rating_review=rating_review,
            user=user,
            message=validated_data['message']
        )
        
        return reply

class ShopRatingReviewSerializer(serializers.ModelSerializer):
    service_id = serializers.IntegerField(source='service.id', read_only=True)
    service_name = serializers.CharField(source='service.title', read_only=True)
    user_id = serializers.IntegerField(source='user.id', read_only=True)
    user_name = serializers.CharField(source='user.name', read_only=True)
    user_img = serializers.ImageField(source='user.profile_image', read_only=True)
    reply = ReplySerializer(source='replies', many=True, read_only=True)
    
    class Meta:
        model = RatingReview
        fields = [
            'id', 'service_id', 'service_name', 'rating', 'review', 
            'user_id', 'user_name', 'user_img', 'reply', 'created_at'
        ]
    
    def to_representation(self, instance):
        rep = super().to_representation(instance)
        request = self.context.get('request')
        
        # Add absolute URL for user image
        if instance.user and instance.user.profile_image and request:
            rep['user_img'] = request.build_absolute_uri(instance.user.profile_image.url)
        elif instance.user and instance.user.profile_image:
            rep['user_img'] = instance.user.profile_image.url
        
        return rep

class MessageSerializer(serializers.ModelSerializer):
    sender_email = serializers.CharField(source="sender.email", read_only=True)
    sender_id = serializers.SerializerMethodField()
    thread_id = serializers.IntegerField(source="thread.id", read_only=True)

    class Meta:
        model = Message
        fields = ["id", "thread_id", "sender_id", "sender_email", "content", "timestamp", "is_read"]

    def get_sender_id(self, obj):
        # If the sender is the shop owner, return the shop id; otherwise return the user id
        try:
            if obj.thread and obj.thread.shop and obj.thread.shop.owner_id == obj.sender_id:
                return obj.thread.shop_id
        except Exception:
            pass
        return obj.sender_id

class ChatThreadSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True, read_only=True)
    shop_name = serializers.CharField(source="shop.name", read_only=True)
    user_email = serializers.CharField(source="user.email", read_only=True)
    user_name = serializers.CharField(source="user.name", read_only=True)
    user_img = serializers.ImageField(source="user.profile_image", read_only=True)
    shop_img = serializers.ImageField(source="shop.shop_img", read_only=True)
    class Meta:
        model = ChatThread
        fields = [
            "id",
            "shop",
            "shop_name",
            "shop_img",
            "user",
            "user_email",
            "user_name",
            "user_img",
            "messages",
            "created_at",
        ]

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        request = self.context.get('request')

        # Absolute URLs for images if request available
        if instance.shop and instance.shop.shop_img:
            rep['shop_img'] = (
                request.build_absolute_uri(instance.shop.shop_img.url)
                if request else instance.shop.shop_img.url
            )

        if instance.user and getattr(instance.user, 'profile_image', None):
            if instance.user.profile_image:
                rep['user_img'] = (
                    request.build_absolute_uri(instance.user.profile_image.url)
                    if request else instance.user.profile_image.url
                )

        return rep

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "message", "notification_type", "data", "is_read", "created_at"]

class DeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = ["fcm_token", "device_token", "device_type"]

class RevenueSerializer(serializers.ModelSerializer):
    shop_id = serializers.ReadOnlyField(source='shop.id')

    class Meta:
        model = Revenue
        fields = ['id', 'shop_id', 'revenue', 'timestamp']

class SuggestionSerializer(serializers.Serializer):
    suggestion_title = serializers.CharField()
    short_description = serializers.CharField()
    category = serializers.ChoiceField(choices=["discount", "marketing", "operational"])

class CouponSerializer(serializers.ModelSerializer):
    # Use PrimaryKeyRelatedField for multiple services
    services = serializers.PrimaryKeyRelatedField(
        queryset=Service.objects.all(),
        many=True
    )

    class Meta:
        model = Coupon
        fields = [
            'id', 'code', 'description', 'amount', 'in_percentage', 
            'discount_type', 'shop', 'services', 'validity_date', 
            'is_active', 'max_usage_per_user', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'code', 'discount_type', 'created_at', 'updated_at']

    def validate_validity_date(self, value):
        if value < timezone.now().date():
            raise serializers.ValidationError("Validity date cannot be in the past")
        return value

    def create(self, validated_data):
        services = validated_data.pop('services', [])
        coupon = super().create(validated_data)
        if services:
            coupon.services.set(services)
        return coupon

    def update(self, instance, validated_data):
        services = validated_data.pop('services', None)
        coupon = super().update(instance, validated_data)
        if services is not None:
            coupon.services.set(services)
        return coupon

class UserCouponRetrieveSerializer(serializers.Serializer):
    shop_id = serializers.IntegerField()
    service_id = serializers.IntegerField()

    def validate(self, attrs):
        shop_id = attrs.get('shop_id')
        service_id = attrs.get('service_id')

        # Fetch all active coupons for this shop and service
        coupon_qs = Coupon.objects.filter(
            shop_id=shop_id,
            services__id=service_id,  # ManyToManyField
            is_active=True
        )

        if not coupon_qs.exists():
            raise serializers.ValidationError(
                "No active coupon found for this shop and service."
            )

        # Attach all matching coupons
        attrs['coupons'] = coupon_qs
        return attrs