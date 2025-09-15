from rest_framework import serializers
from .models import Payment, Booking

class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ['id', 'booking', 'user', 'amount', 'currency', 'status', 'stripe_payment_intent_id']
        read_only_fields = ['id', 'status', 'stripe_payment_intent_id', 'created_at', 'updated_at']

class BookingSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    shop_name = serializers.CharField(source='shop.name', read_only=True)
    slot_time = serializers.DateTimeField(source='slot.start_time', read_only=True)  # Adjust if your SlotBooking uses a different field

    class Meta:
        model = Booking
        fields = [
            'id',
            'user',
            'user_email',
            'shop',
            'shop_name',
            'slot',
            'slot_time',
            'status',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'user_email', 'shop_name', 'slot_time', 'created_at', 'updated_at']
