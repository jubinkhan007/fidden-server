# subscriptions/views.py
import stripe
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from .models import SubscriptionPlan, ShopSubscription
from api.models import Shop
from .serializers import SubscriptionPlanSerializer

stripe.api_key = settings.STRIPE_SECRET_KEY

class SubscriptionPlanListView(APIView):
    """
    Lists all available subscription plans (Momentum, Icon).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Exclude the free 'Foundation' plan from the list of purchasable plans
        plans = SubscriptionPlan.objects.exclude(name=SubscriptionPlan.FOUNDATION)
        serializer = SubscriptionPlanSerializer(plans, many=True)
        return Response(serializer.data)

class CreateSubscriptionCheckoutSessionView(APIView):
    """
    Creates a Stripe Checkout session for a shop owner to subscribe to a plan.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        plan_id = request.data.get('plan_id')
        if not plan_id:
            return Response({"error": "plan_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            plan = SubscriptionPlan.objects.get(id=plan_id)
            shop = request.user.shop
        except (SubscriptionPlan.DoesNotExist, Shop.DoesNotExist):
            return Response({"error": "Invalid Plan or Shop."}, status=status.HTTP_404_NOT_FOUND)

        if not plan.stripe_price_id:
            return Response({"error": "Stripe Price ID not configured for this plan."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        try:
            checkout_session = stripe.checkout.Session.create(
                mode='subscription',
                line_items=[{
                    'price': plan.stripe_price_id,
                    'quantity': 1,
                }],
                success_url=settings.STRIPE_SUCCESS_URL + '?session_id={CHECKOUT_SESSION_ID}',
                cancel_url=settings.STRIPE_CANCEL_URL,
                # Store shop_id to identify the user in the webhook
                client_reference_id=shop.id,
            )
            return Response({'url': checkout_session.url}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CancelSubscriptionView(APIView):
    """
    Cancels a user's active paid subscription and reverts them to the Foundation plan.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            shop = request.user.shop
            shop_subscription = shop.subscription
        except Shop.DoesNotExist:
            return Response({"error": "Shop not found."}, status=status.HTTP_404_NOT_FOUND)

        # If there's no Stripe ID, they are already on the free plan
        if not shop_subscription.stripe_subscription_id:
            return Response({"message": "You are currently on the free Foundation plan."}, status=status.HTTP_200_OK)

        try:
            # Cancel the subscription in Stripe immediately
            stripe.Subscription.delete(shop_subscription.stripe_subscription_id)
            
            # Revert to the Foundation plan in our database
            foundation_plan = SubscriptionPlan.objects.get(name=SubscriptionPlan.FOUNDATION)
            shop_subscription.plan = foundation_plan
            shop_subscription.status = ShopSubscription.STATUS_ACTIVE
            shop_subscription.stripe_subscription_id = None
            shop_subscription.start_date = timezone.now()
            shop_subscription.end_date = timezone.now() + relativedelta(years=100) # Long expiry for free plan
            shop_subscription.save()
            
            return Response({"message": "Subscription cancelled successfully. You are now on the Foundation plan."}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)