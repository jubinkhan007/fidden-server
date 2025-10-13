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
from decimal import Decimal
from .models import SubscriptionPlan, ShopSubscription
from api.models import Shop
from .serializers import SubscriptionPlanSerializer
from payments.models import UserStripeCustomer
import logging
from datetime import timezone as dt_timezone


logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY

def _get_customer_id(user):
    # Adjust to your schema
    return (
        getattr(user, "stripe_customer_id", None)
        or getattr(getattr(user, "profile", None), "stripe_customer_id", None)
    )

def _ensure_shop_customer_id(shop) -> str:
    """
    Ensure there's a Stripe Customer for the SHOP OWNER and return its id.
    We do NOT rely on or write any field on Shop.
    """
    owner = shop.owner
    usc, _ = UserStripeCustomer.objects.get_or_create(user=owner)
    if not usc.stripe_customer_id:
        sc = stripe.Customer.create(
            email=owner.email,
            name=getattr(owner, "name", "") or owner.email,
            metadata={"user_id": str(owner.id)},
        )
        usc.stripe_customer_id = sc.id
        usc.save(update_fields=["stripe_customer_id"])
    return usc.stripe_customer_id

class SubscriptionDetailsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        stripe.api_key = settings.STRIPE_SECRET_KEY
        ai_price_id = getattr(settings, "STRIPE_AI_PRICE_ID", None)

        plan = None
        status = "none"
        renews_on = None
        expires_on = None          # 👈 NEW
        cancel_at_period_end = False
        ai_state = "not_enabled"
        ai_legacy = False

        # find shop
        try:
            shop = request.user.shop
        except Shop.DoesNotExist:
            shop = None

        # Prefer DB
        shop_sub = getattr(shop, "subscription", None) if shop else None
        if shop_sub and shop_sub.plan:
            plan = shop_sub.plan
            # if you store a long free-plan expiry, surface it; otherwise None
            if shop_sub.end_date:
                expires_on = shop_sub.end_date.astimezone(dt_timezone.utc).isoformat()


            if shop_sub.stripe_subscription_id:
                try:
                    s = stripe.Subscription.retrieve(shop_sub.stripe_subscription_id)
                    status = s.get("status", "none")
                    cpe = s.get("current_period_end")
                    if cpe:
                        # Next billing date (and also the end of the current period)
                        renews_on = timezone.datetime.fromtimestamp(int(cpe), tz=dt_timezone.utc).isoformat()
                        expires_on = renews_on  # 👈 NEW: Stripe period end
                    cancel_at_period_end = bool(s.get("cancel_at_period_end"))
                except Exception:
                    pass
            else:
                status = "none"

        # If plan still None, optionally fall back to Stripe (active-ish only)…
        if plan is None and shop:
            try:
                owner_cus = _ensure_shop_customer_id(shop)
                subs = stripe.Subscription.list(
                    customer=owner_cus,
                    status="all",
                    expand=["data.items.data.price"],
                    limit=20,
                )
                ALLOWED = {"active", "trialing", "past_due"}
                priority = {"active": 3, "trialing": 2, "past_due": 1}
                chosen, best = None, -1
                for s in subs.get("data", []):
                    st = s.get("status")
                    if st not in ALLOWED:
                        continue
                    sc = priority.get(st, 0)
                    if sc > best:
                        chosen, best = s, sc

                if chosen:
                    status = chosen.get("status", "none")
                    cpe = chosen.get("current_period_end")
                    if cpe:
                        renews_on = timezone.datetime.fromtimestamp(int(cpe), tz=dt_timezone.utc).isoformat()
                        expires_on = renews_on  # 👈 NEW
                    cancel_at_period_end = bool(chosen.get("cancel_at_period_end"))

                    price_ids = [it["price"]["id"] for it in chosen["items"]["data"]]
                    base_plan = (SubscriptionPlan.objects
                                 .filter(stripe_price_id__in=price_ids)
                                 .order_by("id").first())
                    if base_plan:
                        plan = base_plan

                    ai_price_id and ai_price_id in price_ids and (ai_state := "addon_active")
            except Exception:
                pass

        # Final fallback → Foundation
        if plan is None:
            plan = (SubscriptionPlan.objects.filter(name__iexact=SubscriptionPlan.FOUNDATION).first()
                    or SubscriptionPlan.objects.order_by("id").first())
            status = "none"
            renews_on = renews_on or None
            # keep expires_on as-is (may be None or long free-plan date if set above)

        # AI override if plan includes it
        if getattr(plan, "ai_assistant", "") == "included":
            ai_state = "included"

        commission = plan.commission_rate if plan.commission_rate is not None else Decimal("0.10")

        payload = {
            "plan": SubscriptionPlanSerializer(plan).data,
            "status": status,
            "renews_on": renews_on,
            "expires_on": expires_on,             # 👈 NEW in response
            "cancel_at_period_end": cancel_at_period_end,
            "commission_rate": str(commission),
            "ai": {"state": ai_state, "legacy": ai_legacy, "price_id": ai_price_id},
        }
        return Response(payload, status=200)


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

# subscriptions/views.py

class CreateSubscriptionCheckoutSessionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        plan_id = request.data.get('plan_id')
        if not plan_id:
            return Response({"error": "plan_id is required.", "code": "PLAN_ID_REQUIRED"},
                            status=status.HTTP_400_BAD_REQUEST)

        # 1) Validate plan
        try:
            plan = SubscriptionPlan.objects.get(id=plan_id)
        except SubscriptionPlan.DoesNotExist:
            return Response({"error": "Plan not found.", "code": "PLAN_NOT_FOUND"},
                            status=status.HTTP_404_NOT_FOUND)

        # 2) Validate shop (user must have created one)
        try:
            shop = request.user.shop
        except Shop.DoesNotExist:
            # 409 is good for “precondition not met”; 400 also fine
            return Response({"error": "Create a shop before purchasing a subscription.",
                             "code": "NO_SHOP"},
                            status=status.HTTP_409_CONFLICT)

        if not plan.stripe_price_id:
            return Response({"error": "Stripe Price ID not configured for this plan.",
                             "code": "MISSING_STRIPE_PRICE"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        try:
            customer_id = _ensure_shop_customer_id(shop)
            checkout_session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": plan.stripe_price_id, "quantity": 1}],
            success_url="myapp://subscription/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url="myapp://subscription/cancel",
            client_reference_id=str(shop.id),
            subscription_data={"metadata": {"shop_id": str(shop.id), "plan_id": str(plan.id)}},
        )

            return Response({'url': checkout_session.url}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e), "code": "STRIPE_ERROR"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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