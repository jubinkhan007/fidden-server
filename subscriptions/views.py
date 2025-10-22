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
# add near the top
from django.views.generic import View
from django.http import HttpResponse
from django.urls import reverse


logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY



APP_SCHEME = "myapp"  # your app scheme

_HTML = """
<!doctype html><html><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Returning to app…</title>
<script>
  window.onload = function(){
    var link = "%(deeplink)s";
    // try to open app
    window.location.href = link;
    // show fallback button shortly after
    setTimeout(function(){
      var b = document.getElementById('fallback');
      if (b) b.style.display = 'block';
    }, 800);
  };
</script>
<style>body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;padding:24px}
a.btn{background:#635bff;color:#fff;padding:12px 16px;border-radius:8px;text-decoration:none}
#fallback{display:none}</style>
</head><body>
  <h2>Finishing up…</h2>
  <p>If nothing happens, tap the button below to return to the app.</p>
  <p id="fallback"><a class="btn" href="%(deeplink)s">Open Fidden</a></p>
</body></html>
"""

class CheckoutReturnView(View):
    def get(self, request):
        session_id = request.GET.get("session_id", "")
        deeplink = f"{APP_SCHEME}://subscription/success?session_id={session_id}"
        return HttpResponse(_HTML % {"deeplink": deeplink})

class CheckoutCancelView(View):
    def get(self, request):
        deeplink = f"{APP_SCHEME}://subscription/cancel"
        return HttpResponse(_HTML % {"deeplink": deeplink})


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
                        # Next billing (Stripe)
                        renews_on = timezone.datetime.fromtimestamp(int(cpe), tz=dt_timezone.utc).isoformat()
                    # DO NOT overwrite expires_on here; keep DB value below
                    cancel_at_period_end = bool(s.get("cancel_at_period_end"))
                except Exception:
                    pass
            else:
                status = "none"

            # Always prefer DB for the current period window we show in the app
            if shop_sub.end_date:
                expires_on = shop_sub.end_date.astimezone(dt_timezone.utc).isoformat()

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

        #  Determine AI state correctly (do NOT reset it earlier)
        ai_state = "none"
        if shop_sub:
            # Included automatically for Icon plan
            if shop_sub.plan and shop_sub.plan.ai_assistant == SubscriptionPlan.AI_INCLUDED:
                ai_state = "included"
            # Purchased as add-on
            elif shop_sub.has_ai_addon:
                ai_state = "addon_active"
            # Available for Foundation or Momentum
            elif shop_sub.plan and shop_sub.plan.name in (
                SubscriptionPlan.FOUNDATION,
                SubscriptionPlan.MOMENTUM,
            ):
                ai_state = "available"

        payload = {
            "plan": SubscriptionPlanSerializer(plan).data,
            "status": status,
            "renews_on": renews_on,
            "expires_on": expires_on,
            "cancel_at_period_end": cancel_at_period_end,
            "commission_rate": str(commission),
            "ai": {
                "state": ai_state,
                "legacy": False,
                "price_id": ai_price_id,
            },
        }
        return Response(payload, status=200)


class CreateAIAddonCheckoutSessionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            shop = request.user.shop
            # Get the subscription *object* to check flags
            shop_sub = getattr(shop, "subscription", None)
            if not shop_sub:
                return Response({"error": "Shop subscription details not found."}, status=status.HTTP_404_NOT_FOUND)

        except Shop.DoesNotExist:
            return Response({"error": "Create a shop first."}, status=status.HTTP_404_NOT_FOUND)

        # Basic eligibility check (already existing logic - combined for clarity)
        if shop_sub.has_ai_addon:
             return Response({"error": "AI Assistant add-on already active."}, status=status.HTTP_400_BAD_REQUEST)
        if getattr(shop_sub.plan, 'ai_assistant', 'addon') == 'included':
             return Response({"error": "AI Assistant already included in your plan."}, status=status.HTTP_400_BAD_REQUEST)
        # Add any other plan restrictions if needed

        ai_price_id = getattr(settings, "STRIPE_AI_PRICE_ID", None)
        if not ai_price_id:
            return Response({"error": "AI add-on price not configured."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        promo_code_input = request.data.get("promo_code", None)
        legacy_promo_code_id = getattr(settings, "STRIPE_LEGACY_PROMO_CODE_ID", None)

        success_url = request.build_absolute_uri(reverse("checkout_return")) + "?session_id={CHECKOUT_SESSION_ID}"
        cancel_url  = request.build_absolute_uri(reverse("checkout_cancel"))

        try:
            customer_id = _ensure_shop_customer_id(shop)
            
            checkout_params = {
                "mode": "subscription",
                "customer": customer_id,
                "line_items": [{"price": ai_price_id, "quantity": 1}],
                "success_url": success_url,
                "cancel_url": cancel_url,
                "client_reference_id": str(shop.id),
                "subscription_data": {
                    "metadata": {"shop_id": str(shop.id), "addon": "ai_assistant"}
                },
                "allow_promotion_codes": True, # Allow other codes by default
            }

            # --- LEGACY500 PROMO CODE LOGIC ---
            if promo_code_input and promo_code_input.upper() == "LEGACY500":
                
                # 1. Check if user already used this promo
                if shop_sub.legacy_ai_promo_used:
                    logger.warning(f"Shop {shop.id} attempted to reuse LEGACY500 promo.")
                    return Response(
                        {"error": "This promotion code has already been redeemed for your account."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                if not legacy_promo_code_id:
                     logger.error("LEGACY500 code entered, but STRIPE_LEGACY_PROMO_CODE_ID not set.")
                     return Response({"error": "Legacy promotion configuration error."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

                # 2. Check Stripe Promo Code status (active and within limit)
                try:
                    stripe_promo = stripe.PromotionCode.retrieve(legacy_promo_code_id, expand=["coupon"])
                    
                    # Check if promotion code itself is active
                    if not stripe_promo.active:
                        logger.warning(f"LEGACY500 promotion code ID {legacy_promo_code_id} is inactive in Stripe.")
                        return Response({"error": "This promotion code is no longer valid."}, status=status.HTTP_400_BAD_REQUEST)
                        
                    # Check the underlying coupon's redemption count
                    coupon = stripe_promo.coupon
                    if coupon.times_redeemed >= coupon.max_redemptions:
                        logger.warning(f"LEGACY500 coupon ID {coupon.id} has reached its redemption limit ({coupon.times_redeemed}/{coupon.max_redemptions}).")
                        # Optionally deactivate the promotion code in Stripe now
                        # stripe.PromotionCode.update(legacy_promo_code_id, active=False)
                        return Response({"error": "This promotion code has reached its redemption limit."}, status=status.HTTP_400_BAD_REQUEST)

                except stripe.error.InvalidRequestError as e:
                     # Handle case where Promo Code ID is invalid
                     if "No such promotion_code" in str(e):
                          logger.error(f"STRIPE_LEGACY_PROMO_CODE_ID '{legacy_promo_code_id}' is invalid or does not exist.")
                          return Response({"error": "Legacy promotion configuration error."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                     raise e # Re-raise other Stripe errors

                # 3. Apply the discount automatically
                checkout_params.pop("allow_promotion_codes", None)
                checkout_params["discounts"] = [{"promotion_code": legacy_promo_code_id}]
                logger.info(f"Applying LEGACY500 promo code ID: {legacy_promo_code_id} for shop {shop.id}")

            # --- END LEGACY500 LOGIC ---

            checkout_session = stripe.checkout.Session.create(**checkout_params)
            return Response({"url": checkout_session.url}, status=status.HTTP_200_OK)
            
        except stripe.error.InvalidRequestError as e:
             # Handle specific errors like expired promo codes if needed
             logger.error(f"Stripe InvalidRequestError for AI add-on checkout: {e}")
             return Response({"error": str(e), "code": "STRIPE_INVALID_REQUEST"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception("Stripe error creating checkout session for AI add-on: %s", e)
            return Response({"error": "Could not create checkout session.", "code": "STRIPE_ERROR"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response({"url": checkout_session.url}, status=200)



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
        # 1) Validate input
        plan_id = request.data.get("plan_id")
        if not plan_id:
            return Response(
                {"error": "plan_id is required.", "code": "PLAN_ID_REQUIRED"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2) Load plan
        try:
            plan = SubscriptionPlan.objects.get(id=plan_id)
        except SubscriptionPlan.DoesNotExist:
            return Response(
                {"error": "Plan not found.", "code": "PLAN_NOT_FOUND"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not plan.stripe_price_id:
            return Response(
                {"error": "Stripe Price ID not configured for this plan.", "code": "MISSING_STRIPE_PRICE"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # 3) Load shop for current owner
        try:
            shop = request.user.shop
        except Shop.DoesNotExist:
            return Response(
                {"error": "Create a shop before purchasing a subscription.", "code": "NO_SHOP"},
                status=status.HTTP_409_CONFLICT,
            )

        # 4) Build success/cancel HTTPS pages that bounce back to the app
        success_url = request.build_absolute_uri(reverse("checkout_return")) + "?session_id={CHECKOUT_SESSION_ID}"
        cancel_url  = request.build_absolute_uri(reverse("checkout_cancel"))

        # 5) Create Stripe Checkout Session
        try:
            customer_id = _ensure_shop_customer_id(shop)

            checkout_session = stripe.checkout.Session.create(
                mode="subscription",
                customer=customer_id,
                line_items=[{"price": plan.stripe_price_id, "quantity": 1}],
                success_url=success_url,   # HTTPS → your server → deep link
                cancel_url=cancel_url,     # HTTPS → your server → deep link
                client_reference_id=str(shop.id),
                subscription_data={
                    "metadata": {"shop_id": str(shop.id), "plan_id": str(plan.id)}
                },
            )
            return Response({"url": checkout_session.url}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception("Stripe error creating checkout session: %s", e)
            return Response({"error": str(e), "code": "STRIPE_ERROR"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




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