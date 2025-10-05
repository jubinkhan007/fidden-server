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
    Ensure there's a Stripe Customer (on the platform account) for the shop OWNER,
    persist that id onto the Shop, and return it.
    """
    # Fast path: already saved on Shop
    cid = getattr(shop, "stripe_customer_id", None)
    if cid:
        return cid

    # Reuse/ensure the owner's customer
    owner = shop.owner
    usc, _ = UserStripeCustomer.objects.get_or_create(user=owner)
    if not usc.stripe_customer_id:
        sc = stripe.Customer.create(
            email=owner.email,
            name=getattr(owner, "name", "") or owner.email,
        )
        usc.stripe_customer_id = sc.id
        usc.save(update_fields=["stripe_customer_id"])

    # Mirror to Shop for quick lookup next time
    if shop.stripe_customer_id != usc.stripe_customer_id:
        shop.stripe_customer_id = usc.stripe_customer_id
        shop.save(update_fields=["stripe_customer_id"])

    return shop.stripe_customer_id


class SubscriptionDetailsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        stripe.api_key = settings.STRIPE_SECRET_KEY
        ai_price_id = getattr(settings, "STRIPE_AI_PRICE_ID", None)

        plan = None
        status = "none"
        renews_on = None
        cancel_at_period_end = False
        ai_state = "not_enabled"
        ai_legacy = False

        # 1) Find the user's shop (if any)
        try:
            shop = request.user.shop
        except Shop.DoesNotExist:
            shop = None

        # 2) Prefer our DB (source of truth)
        shop_sub = None
        if shop:
            shop_sub = getattr(shop, "subscription", None)
            if shop_sub and shop_sub.plan:
                plan = shop_sub.plan
                # If we have a Stripe subscription id, we can ask Stripe for status/period_end
                if shop_sub.stripe_subscription_id:
                    try:
                        s = stripe.Subscription.retrieve(shop_sub.stripe_subscription_id)
                        status = s.get("status", "none")
                        cpe = s.get("current_period_end")
                        if cpe:
                            renews_on = timezone.datetime.fromtimestamp(int(cpe), tz=timezone.utc).isoformat()
                        cancel_at_period_end = bool(s.get("cancel_at_period_end"))
                    except Exception:
                        # If Stripe is unreachable, keep DB plan and default status
                        pass
                else:
                    # No Stripe sub id → we treat as free/Foundation (status 'none')
                    status = "none"

        # 3) If we still didn't determine a plan from DB, fallback to Stripe (only active-ish)
        if plan is None and shop:
            customer_id = getattr(shop, "stripe_customer_id", None)
            if customer_id:
                try:
                    subs = stripe.Subscription.list(
                        customer=customer_id,
                        status="all",
                        expand=["data.items.data.price"],  # keep depth <= 4
                        limit=20,
                    )
                    # pick only “current” statuses
                    ALLOWED = {"active", "trialing", "past_due"}
                    chosen = None
                    best_score = -1
                    priority = {"active": 3, "trialing": 2, "past_due": 1}
                    for s in subs.get("data", []):
                        st = s.get("status")
                        if st not in ALLOWED:
                            continue
                        sc = priority.get(st, 0)
                        if sc > best_score:
                            chosen, best_score = s, sc

                    if chosen:
                        status = chosen.get("status", "none")
                        cpe = chosen.get("current_period_end")
                        if cpe:
                            renews_on = timezone.datetime.fromtimestamp(int(cpe), tz=timezone.utc).isoformat()
                        cancel_at_period_end = bool(chosen.get("cancel_at_period_end"))

                        price_ids = [it["price"]["id"] for it in chosen["items"]["data"]]
                        base_plan = (SubscriptionPlan.objects
                                     .filter(stripe_price_id__in=price_ids)
                                     .order_by("id")
                                     .first())
                        if base_plan:
                            plan = base_plan

                        if ai_price_id and ai_price_id in price_ids:
                            ai_state = "addon_active"

                        # Optional: legacy promo example
                        discount = chosen.get("discount")
                        promo_id = discount.get("promotion_code") if discount else None
                        if promo_id:
                            try:
                                promo = stripe.PromotionCode.retrieve(promo_id)
                                if promo and promo.get("code") == "LEGACY500":
                                    ai_legacy = True
                                    ai_state = "included"
                            except Exception:
                                pass
                except Exception:
                    # Stripe unreachable – ignore
                    pass

        # 4) Final fallback → Foundation
        if plan is None:
            plan = (SubscriptionPlan.objects.filter(name__iexact=SubscriptionPlan.FOUNDATION).first()
                    or SubscriptionPlan.objects.order_by("id").first())
            status = "none"
            renews_on = None
            cancel_at_period_end = False

        # 5) AI state from plan
        if getattr(plan, "ai_assistant", "") == "included":
            ai_state = "included"

        # 6) Commission: use the plan’s value, default only if truly missing
        commission = plan.commission_rate
        if commission is None:
            commission = Decimal("0.10")

        payload = {
            "plan": SubscriptionPlanSerializer(plan).data,
            "status": status,
            "renews_on": renews_on,
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

class CreateSubscriptionCheckoutSessionView(APIView):
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
            return Response({"error": "Stripe Price ID not configured for this plan."},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        try:
            # 👇 FIX: ensure & use a platform Customer for the shop owner
            customer_id = _ensure_shop_customer_id(shop)

            checkout_session = stripe.checkout.Session.create(
                mode='subscription',
                customer=customer_id,  # 👈 was undefined before
                line_items=[{'price': plan.stripe_price_id, 'quantity': 1}],
                success_url=settings.STRIPE_SUCCESS_URL + '?session_id={CHECKOUT_SESSION_ID}',
                cancel_url=settings.STRIPE_CANCEL_URL,
                client_reference_id=shop.id,   # used by your webhook to locate the shop
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