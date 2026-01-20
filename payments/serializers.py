from rest_framework import serializers
from stripe import Source
from .models import Payment, Booking, Refund, TransactionLog, CouponUsage, can_use_coupon
from api.models import Coupon
from django.db.models import Avg, Count
from django.utils.timezone import now

class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ['id', 'booking', 'user', 'amount', 'currency', 'status', 'stripe_payment_intent_id']
        read_only_fields = ['id', 'status', 'stripe_payment_intent_id', 'created_at', 'updated_at']

class RefundSerializer(serializers.ModelSerializer):
    class Meta:
        model = Refund
        fields = ["id", "amount", "status", "reason", "stripe_refund_id", "created_at"]

class userBookingSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    shop_name = serializers.CharField(source='shop.name', read_only=True)
    shop_address = serializers.CharField(source='shop.address', read_only=True)
    shop_img = serializers.SerializerMethodField()  #  custom field for absolute URL
    slot_time = serializers.DateTimeField(source='slot.start_time', read_only=True)
    service_id = serializers.CharField(source='slot.service.id', read_only=True)
    service_title = serializers.CharField(source='slot.service.title', read_only=True)
    service_img = serializers.SerializerMethodField()  # V1 Fix: for booking list display
    service_duration = serializers.CharField(source='slot.service.duration', read_only=True)

    avg_rating = serializers.SerializerMethodField()
    total_reviews = serializers.SerializerMethodField()
    refund = RefundSerializer(source="payment.refund", read_only=True)
    add_on_services = serializers.SerializerMethodField()
    shop_timezone = serializers.SerializerMethodField()
    
    # Fidden Pay checkout fields
    deposit_status = serializers.CharField(source='payment.deposit_status', read_only=True, allow_null=True)
    deposit_amount = serializers.DecimalField(source='payment.deposit_amount', read_only=True, max_digits=10, decimal_places=2)
    service_price = serializers.DecimalField(source='payment.service_price', read_only=True, max_digits=10, decimal_places=2, allow_null=True)
    remaining_amount = serializers.DecimalField(source='payment.remaining_amount', read_only=True, max_digits=10, decimal_places=2)
    checkout_initiated = serializers.SerializerMethodField()

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
            'service_id',
            'service_title',
            'service_img',   # V1 Fix: for booking list display
            'service_duration',
            'status',
            'created_at',
            'updated_at',
            'avg_rating',
            'total_reviews',
            'refund',
            'add_on_services',
            'shop_timezone',
            # Fidden Pay
            'deposit_status',
            'deposit_amount',
            'service_price',
            'remaining_amount',
            'checkout_initiated',
        ]
        read_only_fields = fields

    def get_shop_img(self, obj):
        request = self.context.get("request")  #  need request from view
        if obj.shop.shop_img:
            return request.build_absolute_uri(obj.shop.shop_img.url) if request else obj.shop.shop_img.url
        return None

    def get_service_img(self, obj):
        """V1 Fix: Return service image URL for booking display."""
        request = self.context.get("request")
        service = obj.slot.service if obj.slot else None
        if service and service.service_img:
            return request.build_absolute_uri(service.service_img.url) if request else service.service_img.url
        return None

    def get_avg_rating(self, obj):
        avg = obj.shop.ratings.aggregate(avg=Avg("rating"))["avg"]
        return round(avg, 1) if avg else 0

    def get_total_reviews(self, obj):
        return obj.shop.ratings.count()
    
    def get_add_on_services(self, obj):
        """
        Return list of add-on services for this booking
        """
        add_ons = obj.slot.add_ons.all()
        return [
            {
                'title': add_on.service.title,
                'duration': str(add_on.service.duration) if add_on.service.duration else '0',
            }
            for add_on in add_ons
        ]

    def get_shop_timezone(self, obj):
        """Return shop's IANA timezone for client-side conversion."""
        from api.utils.timezone_helpers import get_valid_iana_timezone
        if obj.shop:
            return get_valid_iana_timezone(obj.shop.time_zone)
        return "America/New_York"

    def get_checkout_initiated(self, obj):
        """Return true if owner has initiated checkout."""
        if hasattr(obj, 'payment') and obj.payment:
            return obj.payment.checkout_initiated_at is not None
        return False

    def to_representation(self, instance):
        """
        V1 Fix: Ensure all times are in UTC with Z suffix.
        - slot_time: UTC with Z suffix
        - created_at/updated_at: UTC with Z suffix
        - shop_timezone: IANA timezone for client display conversion
        """
        from api.utils.timezone_helpers import to_utc_iso
        rep = super().to_representation(instance)
        
        # Slot time in UTC
        if instance.slot and instance.slot.start_time:
            rep['slot_time'] = to_utc_iso(instance.slot.start_time)
        
        # Created/Updated times in UTC
        if instance.created_at:
            rep['created_at'] = to_utc_iso(instance.created_at)
        if instance.updated_at:
            rep['updated_at'] = to_utc_iso(instance.updated_at)
        
        return rep

class ownerBookingSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_name = serializers.CharField(source='user.name', read_only=True)
    profile_image = serializers.SerializerMethodField()   
    shop_name = serializers.CharField(source='shop.name', read_only=True)
    shop_niche = serializers.SerializerMethodField()
    slot_time = serializers.DateTimeField(source='slot.start_time', read_only=True)
    service_title = serializers.CharField(source='slot.service.title', read_only=True)
    service_duration = serializers.CharField(source='slot.service.duration', read_only=True) 
    refund = RefundSerializer(source="payment.refund", read_only=True)
    add_on_services = serializers.SerializerMethodField()
    add_ons = serializers.SerializerMethodField()
    shop_timezone = serializers.SerializerMethodField()
    
    # Fidden Pay checkout fields
    deposit_status = serializers.CharField(source='payment.deposit_status', read_only=True, allow_null=True)
    deposit_amount = serializers.DecimalField(source='payment.deposit_amount', read_only=True, max_digits=10, decimal_places=2)
    service_price = serializers.DecimalField(source='payment.service_price', read_only=True, max_digits=10, decimal_places=2, allow_null=True)
    remaining_amount = serializers.DecimalField(source='payment.remaining_amount', read_only=True, max_digits=10, decimal_places=2)
    checkout_initiated = serializers.SerializerMethodField()

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
            'shop_niche',
            'slot',
            'slot_time',
            'service_title',
            'service_duration',   
            'status',
            'refund',
            'add_on_services',
            'add_ons',
            'shop_timezone',
            'created_at',
            'updated_at',
            # Fidden Pay
            'deposit_status',
            'deposit_amount',
            'service_price',
            'remaining_amount',
            'checkout_initiated',
            # Hairstylist prep notes
            'prep_notes',
        ]
        read_only_fields = fields

    def get_profile_image(self, obj):
        request = self.context.get("request")
        if obj.user.profile_image:
            return request.build_absolute_uri(obj.user.profile_image.url) if request else obj.user.profile_image.url
        return None
    
    def get_add_on_services(self, obj):
        """
        Return list of add-on services for this booking
        """
        add_ons = obj.slot.add_ons.all()
        return [
            {
                'title': add_on.service.title,
                'duration': str(add_on.service.duration) if add_on.service.duration else '0',
            }
            for add_on in add_ons
        ]
    
    def get_add_ons(self, obj):
        """
        Return list of add-ons with id, title and price for owner booking display.
        This is the format expected by the Flutter frontend.
        """
        if not obj.slot:
            return []
        add_ons = obj.slot.add_ons.all()
        return [
            {
                'id': add_on.service.id,
                'title': add_on.service.title,
                'price': float(add_on.service.price) if add_on.service.price else 0.0,
            }
            for add_on in add_ons
        ]

    def get_shop_timezone(self, obj):
        """Return shop's IANA timezone for client-side conversion."""
        from api.utils.timezone_helpers import get_valid_iana_timezone
        if obj.shop:
            return get_valid_iana_timezone(obj.shop.time_zone)
        return "America/New_York"

    def get_checkout_initiated(self, obj):
        """Return true if owner has initiated checkout."""
        if hasattr(obj, 'payment') and obj.payment:
            return obj.payment.checkout_initiated_at is not None
        return False
    
    def get_shop_niche(self, obj):
        """Return shop's primary niche for conditional UI rendering."""
        if obj.shop:
            return obj.shop.niche
        return None

    def to_representation(self, instance):
        """
        V1 Fix: Ensure all times are in UTC with Z suffix.
        - slot_time: UTC with Z suffix
        - created_at/updated_at: UTC with Z suffix
        - shop_timezone: IANA timezone for client display conversion
        """
        from api.utils.timezone_helpers import to_utc_iso
        rep = super().to_representation(instance)
        
        # Slot time in UTC
        if instance.slot and instance.slot.start_time:
            rep['slot_time'] = to_utc_iso(instance.slot.start_time)
        
        # Created/Updated times in UTC
        if instance.created_at:
            rep['created_at'] = to_utc_iso(instance.created_at)
        if instance.updated_at:
            rep['updated_at'] = to_utc_iso(instance.updated_at)
        
        return rep
    
class TransactionLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.name', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    shop_name = serializers.CharField(source='shop.name', read_only=True)
    slot_time = serializers.SerializerMethodField()
    service_title = serializers.CharField(source='service.title', read_only=True)
    shop_timezone = serializers.SerializerMethodField()  # V1 Fix

    class Meta:
        model = TransactionLog
        fields = [
            'id', 'transaction_type', 'payment', 'refund', 'user', 'user_name', 'user_email',
            'shop', 'shop_name', 'slot', 'slot_time', 'service', 'service_title',
            'amount', 'currency', 'status', 'created_at', 'shop_timezone'
        ]

    def get_slot_time(self, obj):
        """V1 Fix: Return slot times in UTC format."""
        from api.utils.timezone_helpers import to_utc_iso
        if obj.slot:
            start = to_utc_iso(obj.slot.start_time) or ""
            end = to_utc_iso(obj.slot.end_time) or ""
            return {"start_time": start, "end_time": end}
        return None

    def get_shop_timezone(self, obj):
        """Return shop's IANA timezone for client-side conversion."""
        from api.utils.timezone_helpers import get_valid_iana_timezone
        if obj.shop:
            return get_valid_iana_timezone(obj.shop.time_zone)
        return "America/New_York"

    def to_representation(self, instance):
        """V1 Fix: Ensure created_at is in UTC format."""
        from api.utils.timezone_helpers import to_utc_iso
        rep = super().to_representation(instance)
        if instance.created_at:
            rep['created_at'] = to_utc_iso(instance.created_at)
        return rep

class ApplyCouponSerializer(serializers.Serializer):
    coupon_id = serializers.IntegerField()

    def validate_coupon_id(self, value):
        user = self.context['request'].user

        try:
            coupon = Coupon.objects.get(id=value)
        except Coupon.DoesNotExist:
            raise serializers.ValidationError("Coupon not found.")

        if not coupon.is_active:
            raise serializers.ValidationError("Coupon is inactive.")

        if coupon.validity_date and coupon.validity_date < now().date():
            raise serializers.ValidationError("Coupon has expired.")

        if not can_use_coupon(user, coupon):
            raise serializers.ValidationError("Coupon usage limit reached for this user.")

        self._validated_coupon = coupon  #  store safely
        return value

    @property
    def coupon(self):
        return getattr(self, "_validated_coupon", None)

    def create_usage(self):
        """Record coupon usage for this user"""
        user = self.context['request'].user
        if not self.coupon:
            raise serializers.ValidationError("No coupon available to use.")
        CouponUsage.objects.create(user=user, coupon=self.coupon)
        return self.coupon