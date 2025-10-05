# subscriptions/serializers.py
from rest_framework import serializers
from .models import SubscriptionPlan

class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = [
            "id", "name", "monthly_price", "commission_rate", "stripe_price_id",
            "marketplace_profile", "instant_booking_payments", "automated_reminders",
            "smart_rebooking_prompts", "deposit_customization",
            "priority_marketplace_ranking", "advanced_calendar_tools",
            "auto_followups", "ai_assistant", "performance_analytics",
            "ghost_client_reengagement",
        ]