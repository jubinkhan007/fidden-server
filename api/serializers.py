# api/serializers.py

from rest_framework import serializers

from fidden import settings
from subscriptions.models import SubscriptionPlan
from .models import (
    AIAutoFillSettings,
    PerformanceAnalytics,
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
    Coupon,
    ServiceDisabledTime,
)
from math import radians, cos, sin, asin, sqrt
from django.db.models.functions import Coalesce
from django.db.models import Avg, Count, Q, Value, FloatField
from api.utils.helper_function import get_distance
from django.db import transaction
from django.utils import timezone
from accounts.serializers import UserSerializer


class PerformanceAnalyticsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PerformanceAnalytics
        exclude = ['id', 'shop']

    def to_representation(self, instance):
        """
        Custom representation to filter analytics data based on the user's plan.
        """
        data = super().to_representation(instance)
        plan = self.context.get('plan')

        # For 'Momentum' users, the plan context should be 'basic'.
        if plan == 'basic':
            return {
                'total_revenue': data.get('total_revenue'),
                'total_bookings': data.get('total_bookings'),
                'average_rating': data.get('average_rating'),
            }

        # For 'Icon' users ('advanced' plan) and any other higher tiers,
        # return the full dataset. The view already handles the 'none' case.
        return data

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


class BusinessHoursField(serializers.JSONField):
    """Validates {"mon":[["09:00","14:00"], ...], "thu":[["13:00","17:00"]]}."""
    valid_days = {"mon","tue","wed","thu","fri","sat","sun"}

    def to_internal_value(self, data):
        v = super().to_internal_value(data or {})
        if not isinstance(v, dict):
            raise serializers.ValidationError("business_hours must be an object")
        for day, intervals in v.items():
            if day not in self.valid_days:
                raise serializers.ValidationError(f"Invalid day key: {day}")
            if not isinstance(intervals, list):
                raise serializers.ValidationError(f"{day} must be a list of [start,end] pairs")
            for pair in intervals:
                if (not isinstance(pair, (list, tuple))) or len(pair) != 2:
                    raise serializers.ValidationError(f"{day} items must be [start,end]")
                for t in pair:
                    if not isinstance(t, str) or len(t) != 5 or t[2] != ":":
                        raise serializers.ValidationError(f"Time '{t}' must be 'HH:MM'")
                    hh, mm = t.split(":")
                    try:
                        hh = int(hh); mm = int(mm)
                        assert 0 <= hh <= 23 and 0 <= mm <= 59
                    except Exception:
                        raise serializers.ValidationError(f"Invalid time '{t}'")
                # ensure start < end
                if pair[0] >= pair[1]:
                    raise serializers.ValidationError(f"{day} start must be before end: {pair}")
        return v


class ServiceSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    category = serializers.PrimaryKeyRelatedField(queryset=ServiceCategory.objects.all())

    # ⬇️ owners POST/PUT/PATCH: list of "HH:MM" strings
    disabled_start_times = serializers.ListField(
        child=serializers.CharField(),
        write_only=True,
        required=False
    )
    # ⬇️ GET: returns normalized "HH:MM" list
    disabled_times = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Service
        fields = [
            'id', 'title', 'price', 'discount_price', 'description',
            'service_img', 'category', 'duration', 'capacity', 'is_active',
            'disabled_start_times',   # write
            'disabled_times', "requires_age_18_plus",         # read
        ]
        read_only_fields = ('shop',)

    def get_disabled_times(self, instance):
        return [t.start_time.strftime('%H:%M') for t in instance.disabled_times.all().order_by('start_time')]

    def _parse_times(self, raw_list):
        """
        Accepts items like '10:00', '10:00:00', '10.00', '10-00'
        and returns list[datetime.time]. Raises ValidationError on bad values.
        """
        import re
        from datetime import time
        parsed = []
        for s in raw_list or []:
            val = (s or '').strip()
            if not val:
                continue
            # normalize separators to ':'
            v = re.sub(r'[.\-]', ':', val)
            parts = v.split(':')
            if not (1 <= len(parts) <= 3):
                raise serializers.ValidationError(f"Invalid time: {s}")
            try:
                h = int(parts[0]); m = int(parts[1]) if len(parts) >= 2 else 0
                sec = int(parts[2]) if len(parts) == 3 else 0
                if not (0 <= h < 24 and 0 <= m < 60 and 0 <= sec < 60):
                    raise ValueError
                parsed.append(time(hour=h, minute=m, second=sec))
            except Exception:
                raise serializers.ValidationError(f"Invalid time: {s}")
        return parsed

    def _sync_disabled_times(self, service, raw_list):
        """Idempotently replace the ServiceDisabledTime rows for this service."""
        times = self._parse_times(raw_list)
        # build a set for quick compare
        wanted = {(t.hour, t.minute, t.second) for t in times}

        # current rows
        existing = list(service.disabled_times.all())
        existing_set = {(dt.start_time.hour, dt.start_time.minute, dt.start_time.second) for dt in existing}

        # delete removed
        for dt in existing:
            key = (dt.start_time.hour, dt.start_time.minute, dt.start_time.second)
            if key not in wanted:
                dt.delete()

        # add new
        from datetime import time
        to_add = wanted - existing_set
        ServiceDisabledTime.objects.bulk_create([
            ServiceDisabledTime(service=service, start_time=time(h, m, s))
            for (h, m, s) in to_add
        ])

    def create(self, validated_data):
        disabled_raw = validated_data.pop('disabled_start_times', None)
        service = super().create(validated_data)
        if disabled_raw is not None:
            self._sync_disabled_times(service, disabled_raw)
        return service

    def update(self, instance, validated_data):
        disabled_raw = validated_data.pop('disabled_start_times', None)
        service = super().update(instance, validated_data)
        if disabled_raw is not None:
            self._sync_disabled_times(service, disabled_raw)
        return service

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        request = self.context.get('request')
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
    #  removed services from response
    owner_id = serializers.IntegerField(source='owner.id', read_only=True)
    business_hours = BusinessHoursField(required=False)  
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
            'close_at', 'break_start_time', 'break_end_time', 'about_us', 
            'shop_img', 'close_days', "business_hours", 'owner_id', 'is_verified', 'status', 
            'verification_files', 'uploaded_files', 'is_deposit_required',
            'default_deposit_percentage',
            'free_cancellation_hours', 'cancellation_fee_percentage', 'no_refund_hours'
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
        plan_name = instance.subscription.plan.name

        policy_fields = {
            'is_deposit_required', 'deposit_amount', 'default_deposit_percentage',
            'free_cancellation_hours', 'cancellation_fee_percentage', 'no_refund_hours'
        }

        # Foundation: Cannot change ANY policy fields
        if plan_name == SubscriptionPlan.FOUNDATION:
            for field in policy_fields:
                if field in validated_data:
                    validated_data.pop(field)

        # Momentum: Can only change deposit percentage
        elif plan_name == SubscriptionPlan.MOMENTUM:
            allowed = {'default_deposit_percentage'}  # Only percentage allowed
            for field in policy_fields:
                if field in validated_data and field not in allowed:
                    validated_data.pop(field)

        # Icon: Can change everything (no restrictions)

        # Continue with update...
        instance.status = "pending"
        files = validated_data.pop("verification_files", None)

        # USE super().update() instead of manual field setting
        instance = super().update(instance, validated_data)

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

# api/serializers.py  (SlotSerializer)
class SlotSerializer(serializers.ModelSerializer):
    available = serializers.SerializerMethodField()
    disabled_by_service = serializers.SerializerMethodField()

    class Meta:
        model = Slot
        fields = [
            'id', 'shop', 'service', 'start_time', 'end_time',
            'capacity_left', 'available', 'disabled_by_service'
        ]

    def _local_tod(self, dt):
        # Convert the aware datetime to local timezone, then take the time-of-day
        return timezone.localtime(dt, timezone.get_default_timezone()).time()

    def _disabled_set(self, obj):
        # Set of time-of-day values (datetime.time) configured as disabled for this service
        return set(obj.service.disabled_times.values_list('start_time', flat=True))

    def get_available(self, obj):
        service_capacity_ok = obj.capacity_left > 0
        shop_capacity_ok = obj.service.shop.capacity > 0
        local_tod = self._local_tod(obj.start_time)
        not_disabled = (local_tod not in self._disabled_set(obj))
        return service_capacity_ok and shop_capacity_ok and not_disabled

    def get_disabled_by_service(self, obj):
        local_tod = self._local_tod(obj.start_time)
        return local_tod in self._disabled_set(obj)


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
    is_priority = serializers.SerializerMethodField()  # <- NEW
    boost_score = serializers.IntegerField(read_only=True, default=0)
    def get_shop_img(self, obj):
        request = self.context.get("request")
        img = obj.shop_img
        if img and getattr(img, 'name', None):
            return request.build_absolute_uri(img.url) if request else img.url
        return None

    def get_distance(self, obj):
        user_location = self.context.get("user_location")
        return get_distance(user_location, obj.location)

    def get_badge(self, obj):
        return "Top"

    def get_is_priority(self, obj) -> bool:
        """
        True when the shop’s current subscription plan has priority_marketplace_ranking.
        Falls back to False if no active subscription/plan is present.
        """
        try:
            sub = getattr(obj, "subscription", None)
            if sub and getattr(sub, "is_active", False) and getattr(sub, "plan", None):
                return bool(getattr(sub.plan, "priority_marketplace_ranking", False))
        except Exception:
            pass
        return False

    
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
            'avg_rating', 'review_count', 'distance', 'services', 'reviews',
            'free_cancellation_hours', 'cancellation_fee_percentage', 'no_refund_hours'
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
                ),
                "requires_age_18_plus": s.requires_age_18_plus,
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
            "is_active",
            "requires_age_18_plus" 
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
            "requires_age_18_plus",
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
    last_message = serializers.SerializerMethodField()
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
            "last_message",
            "created_at",
        ]

    def get_last_message(self, obj):
        request = self.context.get('request')
        last_message_only = self.context.get('last_message_only', False)

        if last_message_only:
            last_message = obj.messages.order_by('-timestamp').first()
            if last_message:
                return MessageSerializer(last_message, context={'request': request}).data
        return None

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        request = self.context.get('request')

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
    user = UserSerializer(read_only=True)

    class Meta:
        model = Device
        fields = ["user", "fcm_token", "device_token", "device_type"]

    # def create(self, validated_data):
    #     user = self.context['request'].user
    #     device_token = validated_data['device_token']
    #
    #     # Try to find a device with same token for the logged-in user
    #     try:
    #         device = Device.objects.get(device_token=device_token, user=user)
    #         device.fcm_token = validated_data.get('fcm_token', device.fcm_token)
    #         device.device_type = validated_data.get('device_type', device.device_type)
    #         device.save()
    #         self.instance = device
    #         return device
    #     except Device.DoesNotExist:
    #         # Create new device if not found for this user
    #         device = Device.objects.create(
    #             user=user,
    #             device_token=device_token,
    #             fcm_token=validated_data.get('fcm_token'),
    #             device_type=validated_data.get('device_type', 'android')
    #         )
    #         self.instance = device
    #         return device


    #new function for update the device
    def create(self, validated_data):
        user = self.context['request'].user

        # Get or create device for this user (ensuring only one exists)
        device, created = Device.objects.update_or_create(
            user=user,
            defaults={
                'device_token': validated_data['device_token'],
                'fcm_token': validated_data.get('fcm_token'),
                'device_type': validated_data.get('device_type', 'android')
            }
        )

        self.instance = device
        return device

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
    
class AIAutoFillSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIAutoFillSettings
        fields = [
            'is_active',
            'no_show_window_minutes',
            'auto_fill_scope_hours',
        ]


class AIReportSerializer(serializers.ModelSerializer):
    """
    Serializer for the AI Weekly Report.
    """
    top_selling_service = serializers.CharField(source='get_top_selling_service_display')
    forecast_summary = serializers.CharField(source='get_forecast_summary_display')
    motivational_nudge = serializers.CharField(source='get_motivational_nudge_display')

    class Meta:
        model = PerformanceAnalytics
        fields = [
            'total_appointments',
            'total_revenue',
            'no_shows_filled', # Assuming you add this field later
            'top_selling_service',
            'forecast_summary',
            'motivational_nudge',
            'week_start_date',
        ]

# api/serializers.py

class AiSubscriptionStateSerializer(serializers.Serializer):
    """
    Serializes the 'ai' block by reading from a Shop instance.
    This provides the AI state for the frontend.
    """
    state = serializers.SerializerMethodField()
    legacy = serializers.SerializerMethodField()
    price_id = serializers.SerializerMethodField()

    def get_state(self, shop):
        """
        Determines the AI state based on the shop's subscription.
        """
        sub = getattr(shop, 'subscription', None)
        if not sub or not sub.plan:
            # This should be caught by the view's 403 check,
            # but serves as a fallback.
            return "none" 
        
        if sub.plan.ai_assistant == SubscriptionPlan.AI_INCLUDED:
            return "included"
        if sub.has_ai_addon:
            return "addon_active"
        
        # User is on a plan where AI is 'addon' but hasn't bought it
        return "available"

    def get_legacy(self, shop):
        """
        Checks if the legacy promo has been used.
        """
        sub = getattr(shop, 'subscription', None)
        return getattr(sub, 'legacy_ai_promo_used', False)
    
    def get_price_id(self, shop):
        """
        Returns the globally configured AI Price ID.
        """
        return getattr(settings, "STRIPE_AI_PRICE_ID", None)

from rest_framework import serializers
from .models import WeeklySummary


# api/serializers.py

class WeeklySummarySerializer(serializers.ModelSerializer):
    deep_link = serializers.SerializerMethodField()
    
    # --- ADD THIS LINE ---
    # This tells the serializer to take the 'shop' object from the WeeklySummary
    # and pass it to the AiSubscriptionStateSerializer.
    ai = AiSubscriptionStateSerializer(source='shop', read_only=True)
    # --- END ADD ---

    class Meta:
        model = WeeklySummary
        fields = [
            "id",
            "week_start_date",
            "week_end_date",
            "total_appointments",
            "revenue_generated",
            "rebooking_rate",
            "growth_rate",
            "no_shows_filled",
            "top_service",
            "top_service_count",
            "open_slots_next_week",
            "forecast_estimated_revenue",
            "ai_motivation",
            "ai_recommendations",
            "delivered_channels",
            "deep_link",
            "created_at",
            "ai",  # <-- ADD 'ai' TO THE LIST
        ]

    def get_deep_link(self, obj):
        return f"fidden://weekly-recap/{obj.id}"


# serializers.py
class WeeklySummaryActionSerializer(serializers.Serializer):
    summary_id = serializers.UUIDField()
    preview_only = serializers.BooleanField(required=False, default=False)