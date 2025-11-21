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
from django.urls import reverse
from api.services.paypal import create_subscription, cancel_subscription, revise_subscription

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
            shop_sub = getattr(shop, "subscription", None)
            if not shop_sub:
                return Response({"error": "Shop subscription details not found."}, status=status.HTTP_404_NOT_FOUND)
        except Shop.DoesNotExist:
            return Response({"error": "Create a shop first."}, status=status.HTTP_404_NOT_FOUND)

        # 1. Basic eligibility check (unchanged)
        if shop_sub.has_ai_addon:
             return Response({"error": "AI Assistant add-on already active."}, status=status.HTTP_400_BAD_REQUEST)
        if getattr(shop_sub.plan, 'ai_assistant', 'addon') == 'included':
             return Response({"error": "AI Assistant already included in your plan."}, status=status.HTTP_400_BAD_REQUEST)

        # NEW: Check provider from request body
        provider = request.data.get("provider", "stripe").lower()
        
        # ========== PAYPAL FLOW ==========
        if provider == "paypal":
            try:
                # Find AI add-on plan
                ai_addon_plan = SubscriptionPlan.objects.filter(ai_assistant=SubscriptionPlan.AI_ADDON).first()
                if not ai_addon_plan or not ai_addon_plan.paypal_plan_id:
                    return Response(
                        {"error": "AI add-on is not configured for PayPal."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                return_url = request.build_absolute_uri(reverse("paypal_return"))
                cancel_url = request.build_absolute_uri(reverse("paypal_cancel"))

                paypal_sub_id, approval_url = create_subscription(ai_addon_plan, shop, return_url, cancel_url)

                # Store the PayPal subscription ID for the AI add-on
                shop_sub.ai_paypal_subscription_id = paypal_sub_id
                shop_sub.has_ai_addon = False  # Wait for webhook confirmation
                shop_sub.save()

                return Response(
                    {
                        "url": approval_url,
                        "subscription_id": paypal_sub_id,
                    },
                    status=status.HTTP_200_OK,
                )
            except Exception as e:
                logger.error(f"PayPal error creating AI add-on subscription: {e}", exc_info=True)
                return Response({"error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        # ========== STRIPE FLOW (ORIGINAL) ==========
        ai_price_id = getattr(settings, "STRIPE_AI_PRICE_ID", None)
        if not ai_price_id:
            return Response({"error": "AI add-on price not configured."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        legacy_promo_code_id = getattr(settings, "STRIPE_LEGACY_PROMO_CODE_ID", None)
        apply_legacy_promo = False

        # --- 2. START: AUTOMATIC LEGACY PROMO CHECK ---
        # Instead of checking user input, we proactively check if the user is eligible.
        if legacy_promo_code_id and not shop_sub.legacy_ai_promo_used:
            try:
                # Check Stripe Promo Code status (active and within limit)
                stripe_promo = stripe.PromotionCode.retrieve(legacy_promo_code_id, expand=["coupon"])
                coupon = stripe_promo.coupon
                
                if stripe_promo.active and coupon.times_redeemed < coupon.max_redemptions:
                    # If the code is valid and user hasn't used it, flag it to be applied
                    apply_legacy_promo = True
                    logger.info(f"Shop {shop.id} is eligible for LEGACY500. Applying automatically.")
                else:
                    logger.warning(
                        f"LEGACY500 promo {legacy_promo_code_id} is no longer valid (active={stripe_promo.active}, "
                        f"redeemed={coupon.times_redeemed}/{coupon.max_redemptions})."
                    )
                    
            except stripe.error.InvalidRequestError as e:
                 logger.error(f"Error checking STRIPE_LEGACY_PROMO_CODE_ID '{legacy_promo_code_id}': {e}")
                 # Don't crash, just proceed without the discount.
            except Exception as e:
                 logger.error(f"Unexpected error checking legacy promo code: {e}", exc_info=True)
                 # Don't crash, just proceed without the discount.
        
        elif shop_sub.legacy_ai_promo_used:
            logger.info(f"Shop {shop.id} has already redeemed LEGACY500. Skipping auto-apply.")
        # --- END: AUTOMATIC LEGACY PROMO CHECK ---

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
            }

            # --- 3. APPLY PROMO IF FLAG IS SET ---
            if apply_legacy_promo:
                # Apply the discount automatically
                checkout_params["discounts"] = [{"promotion_code": legacy_promo_code_id}]
                logger.info(f"Automatically applying LEGACY500 promo code ID: {legacy_promo_code_id} for shop {shop.id}")
            else:
                # Otherwise, just allow other codes to be entered manually
                checkout_params["allow_promotion_codes"] = True

            checkout_session = stripe.checkout.Session.create(**checkout_params)
            return Response({"url": checkout_session.url}, status=status.HTTP_200_OK)
            
        except stripe.error.StripeError as e:
             logger.error(f"Stripe error for AI add-on checkout: {e}", exc_info=True)
             return Response({"error": str(e), "code": "STRIPE_ERROR"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception("Unexpected error creating checkout session for AI add-on: %s", e)
            return Response({"error": "Could not create checkout session.", "code": "UNEXPECTED_ERROR"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




class CancelAIAddonView(APIView):
    """
    Cancels the AI Assistant add-on (separate Stripe subscription or item).
    Does not cancel the base subscription plan.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            shop = request.user.shop
            shop_sub = getattr(shop, "subscription", None)
            if not shop_sub:
                return Response({"error": "Shop subscription details not found."}, status=status.HTTP_404_NOT_FOUND)
        except Shop.DoesNotExist:
            return Response({"error": "Shop not found."}, status=status.HTTP_404_NOT_FOUND)

        # ---- 1) Eligibility checks (unchanged) --------------------------------
        if not shop_sub.has_ai_addon:
            return Response({"error": "AI Assistant add-on is not currently active."}, status=status.HTTP_400_BAD_REQUEST)

        if shop_sub.legacy_ai_promo_used:
            return Response({"error": "Cannot cancel a lifetime promotional access."}, status=status.HTTP_400_BAD_REQUEST)

        if getattr(shop_sub.plan, "ai_assistant", "addon") == "included":
            return Response({"error": "AI Assistant is included with your current plan and cannot be cancelled separately."},
                            status=status.HTTP_400_BAD_REQUEST)

        ai_price_id = getattr(settings, "STRIPE_AI_PRICE_ID", None)
        if not ai_price_id:
            logger.error("STRIPE_AI_PRICE_ID is not configured in settings.")
            return Response({"error": "AI add-on configuration error."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # ---- 2) Use the AI subscription IDs (NOT the base plan subscription) ---
        ai_sub_id = getattr(shop_sub, "ai_subscription_id", None)
        ai_item_id = getattr(shop_sub, "ai_subscription_item_id", None)

        if not ai_sub_id:
            # Nothing to cancel in Stripe → clean up local flags
            logger.warning("Shop %s has_ai_addon=True but no ai_subscription_id; cleaning up.", shop.id)
            shop_sub.has_ai_addon = False
            shop_sub.ai_subscription_item_id = None
            shop_sub.save(update_fields=["has_ai_addon", "ai_subscription_item_id"])
            return Response({"error": "AI add-on not found in your active subscription details."}, status=status.HTTP_404_NOT_FOUND)

        try:
            # Expand items w/ price so we can re-derive the item if needed
            sub = stripe.Subscription.retrieve(ai_sub_id, expand=["items.data.price"])
        except stripe.error.InvalidRequestError as e:
            # e.g. "No such subscription"
            logger.warning("Stripe: could not retrieve AI subscription %s for shop %s: %s", ai_sub_id, shop.id, e)
            shop_sub.has_ai_addon = False
            shop_sub.ai_subscription_id = None
            shop_sub.ai_subscription_item_id = None
            shop_sub.save(update_fields=["has_ai_addon", "ai_subscription_id", "ai_subscription_item_id"])
            return Response({"error": "AI add-on not found in your active subscription details."}, status=status.HTTP_404_NOT_FOUND)

        # ---- 3) Ensure we know the correct AI SubscriptionItem ID --------------
        if not ai_item_id:
            it = next((it for it in sub["items"]["data"] if (it.get("price") or {}).get("id") == ai_price_id), None)
            ai_item_id = it["id"] if it else None

        if not ai_item_id:
            logger.warning("AI item not present on AI subscription %s for shop %s; cleaning up.", ai_sub_id, shop.id)
            shop_sub.has_ai_addon = False
            shop_sub.ai_subscription_id = None
            shop_sub.ai_subscription_item_id = None
            shop_sub.save(update_fields=["has_ai_addon", "ai_subscription_id", "ai_subscription_item_id"])
            return Response({"error": "AI add-on not found in your active subscription details."}, status=status.HTTP_404_NOT_FOUND)

        # ---- 4) Cancel: whole sub if single-item, else just remove the item ----
        try:
            if len(sub["items"]["data"]) <= 1:
                # The AI add-on subscription only contains this item → delete the whole subscription
                stripe.Subscription.delete(ai_sub_id)
                logger.info("Deleted AI subscription %s for shop %s", ai_sub_id, shop.id)
            else:
                # Multi-item sub (rare for add-on) → remove just the AI item
                stripe.SubscriptionItem.delete(ai_item_id, proration_behavior="create_prorations")
                logger.info("Removed AI item %s from AI subscription %s for shop %s", ai_item_id, ai_sub_id, shop.id)

            # ---- 5) DB cleanup --------------------------------------------------
            shop_sub.has_ai_addon = False
            shop_sub.ai_subscription_id = None
            shop_sub.ai_subscription_item_id = None
            # legacy_ai_promo_used stays as-is (true if they redeemed lifetime)
            shop_sub.save(update_fields=["has_ai_addon", "ai_subscription_id", "ai_subscription_item_id"])

            return Response({"success": True, "message": "AI Assistant add-on successfully cancelled."}, status=status.HTTP_200_OK)

        except stripe.error.StripeError as e:
            logger.error("Stripe error cancelling AI add-on for shop %s: %s", shop.id, e, exc_info=True)
            return Response({"error": f"Could not cancel add-on with billing provider: {e.user_message or str(e)}"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            logger.error("Unexpected error cancelling AI add-on for shop %s: %s", shop.id, e, exc_info=True)
            return Response({"error": "An unexpected error occurred during cancellation."},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)



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
        provider = (request.data.get("provider") or "stripe").lower().strip()

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

        # 3) Load shop for current owner
        try:
            shop = request.user.shop
        except Shop.DoesNotExist:
            return Response(
                {"error": "Create a shop before purchasing a subscription.", "code": "NO_SHOP"},
                status=status.HTTP_409_CONFLICT,
            )

        # ---------- PAYPAL FLOW ----------
        if provider == "paypal":
            if not plan.paypal_plan_id:
                return Response(
                    {
                        "error": "Plan is not configured for PayPal.",
                        "code": "MISSING_PAYPAL_PLAN",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return_url = request.build_absolute_uri(reverse("paypal_return"))
            cancel_url = request.build_absolute_uri(reverse("paypal_cancel"))

            try:
                paypal_sub_id, approval_url = create_subscription(
                    plan=plan,
                    shop=shop,
                    return_url=return_url,
                    cancel_url=cancel_url,
                )
            except Exception as e:
                logger.exception("PayPal error creating subscription: %s", e)
                return Response(
                    {
                        "error": "Could not create PayPal subscription.",
                        "code": "PAYPAL_ERROR",
                        "detail": str(e),
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            # Persist "pending" PayPal subscription locally
            sub, _ = ShopSubscription.objects.get_or_create(shop=shop)
            sub.provider = ShopSubscription.PROVIDER_PAYPAL
            sub.plan = plan
            sub.paypal_subscription_id = paypal_sub_id
            sub.status = "pending"  # Webhook will move to 'active'
            sub.save()

            return Response(
                {
                    "url": approval_url,
                    "provider": "paypal",
                    "subscription_id": paypal_sub_id,
                },
                status=status.HTTP_200_OK,
            )

        # ---------- STRIPE FLOW (existing behavior) ----------
        if not plan.stripe_price_id:
            return Response(
                {
                    "error": "Stripe Price ID not configured for this plan.",
                    "code": "MISSING_STRIPE_PRICE",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        success_url = request.build_absolute_uri(reverse("checkout_return")) + "?session_id={CHECKOUT_SESSION_ID}"
        cancel_url  = request.build_absolute_uri(reverse("checkout_cancel"))

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
            return Response(
                {
                    "url": checkout_session.url,
                    "provider": "stripe",
                    "session_id": checkout_session.id,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.exception("Stripe error creating checkout session: %s", e)
            return Response(
                {"error": str(e), "code": "STRIPE_ERROR"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )




class CancelSubscriptionView(APIView):
    """
    Cancels a user's active paid subscription by deleting it in Stripe.
    The 'customer.subscription.deleted' webhook will handle downgrading
    the plan in the local database.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            shop = request.user.shop
            shop_subscription = shop.subscription
        except Shop.DoesNotExist:
            return Response({"error": "Shop not found."}, status=status.HTTP_404_NOT_FOUND)
        except ShopSubscription.DoesNotExist:
            # This can happen if the subscription row was deleted, but check plan just in case
            return Response({"error": "Subscription not found."}, status=status.HTTP_404_NOT_FOUND)

        # If there's no Stripe ID, they are already on the free plan
        if not shop_subscription.stripe_subscription_id:
            # Just in case, ensure they are on Foundation
            try:
                foundation_plan = SubscriptionPlan.objects.get(name=SubscriptionPlan.FOUNDATION)
                if shop_subscription.plan != foundation_plan:
                    shop_subscription.plan = foundation_plan
                    shop_subscription.save(update_fields=["plan"])
            except SubscriptionPlan.DoesNotExist:
                pass
            return Response({"message": "You are currently on the free Foundation plan."}, status=status.HTTP_200_OK)

        try:
            # ONLY delete the subscription in Stripe.
            # DO NOT change the local database here.
            stripe.Subscription.delete(shop_subscription.stripe_subscription_id)
            
            logger.info(f"User {request.user.email} initiated Stripe cancellation for sub: {shop_subscription.stripe_subscription_id}")
            
            # The webhook will handle all database changes and Zapier events.
            return Response({"message": "Subscription cancellation initiated. Your plan will be updated shortly."}, status=status.HTTP_200_OK)
        
        except stripe.error.InvalidRequestError as e:
            # Handle cases where the subscription is already canceled in Stripe
            if "No such subscription" in str(e):
                logger.warning(f"Sub {shop_subscription.stripe_subscription_id} not found in Stripe, but was in DB. Forcing downgrade locally.")
                # Force the downgrade locally as Stripe already deleted it.
                try:
                    foundation = SubscriptionPlan.objects.get(name=SubscriptionPlan.FOUNDATION)
                    shop_subscription.plan = foundation
                    shop_subscription.status = ShopSubscription.STATUS_ACTIVE
                    shop_subscription.stripe_subscription_id = None
                    shop_subscription.end_date = timezone.now() + relativedelta(years=100)
                    shop_subscription.save()
                except Exception as db_e:
                    logger.error(f"Failed to force downgrade for sub {shop_subscription.stripe_subscription_id}: {db_e}")
                
                return Response({"message": "Subscription is already inactive."}, status=status.HTTP_200_OK)
            else:
                logger.error(f"Stripe error cancelling subscription: {e}")
                return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            logger.error(f"Unexpected error cancelling subscription: {e}", exc_info=True)
            return Response({"error": "An unexpected error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
class CreatePayPalSubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Body: { "plan_id": <SubscriptionPlan.id> }
        Creates a PayPal subscription and returns approval URL.
        """
        try:
            shop = request.user.shop
        except Shop.DoesNotExist:
             return Response({"detail": "Shop not found"}, status=status.HTTP_404_NOT_FOUND)

        plan_id = request.data.get("plan_id")

        try:
            plan = SubscriptionPlan.objects.get(id=plan_id)
        except SubscriptionPlan.DoesNotExist:
            return Response({"detail": "Invalid plan_id"}, status=status.HTTP_400_BAD_REQUEST)

        if not plan.paypal_plan_id:
            return Response(
                {"detail": "Plan is not configured for PayPal."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return_url = request.build_absolute_uri(reverse("checkout_return")) + "?session_id={CHECKOUT_SESSION_ID}" # PayPal doesn't use session_id like Stripe, but we can adapt or use a different return URL
        # Actually, for PayPal we might want a specific return URL that handles the token. 
        # But to keep it simple and consistent with the app's deep linking:
        return_url = request.build_absolute_uri(reverse("paypal_return")) 
        cancel_url = request.build_absolute_uri(reverse("paypal_cancel"))

        try:
            paypal_sub_id, approval_url = create_subscription(plan, shop, return_url, cancel_url)
        except Exception as e:
             return Response({"detail": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        # Create or update ShopSubscription in "pending" state
        sub, _ = ShopSubscription.objects.get_or_create(shop=shop)
        sub.provider = ShopSubscription.PROVIDER_PAYPAL
        sub.plan = plan
        sub.paypal_subscription_id = paypal_sub_id
        sub.status = "pending"  # until webhook confirms "ACTIVE"
        sub.save()

        return Response(
            {
                "approval_url": approval_url,
                "subscription_id": paypal_sub_id,
            },
            status=status.HTTP_200_OK,
        )

class UpdatePayPalSubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Body: { "plan_id": <SubscriptionPlan.id> }
        Upgrades/Downgrades an existing PayPal subscription.
        """
        try:
            shop = request.user.shop
            sub = shop.subscription
        except (Shop.DoesNotExist, ShopSubscription.DoesNotExist):
             return Response({"detail": "Subscription not found"}, status=status.HTTP_404_NOT_FOUND)

        if sub.provider != ShopSubscription.PROVIDER_PAYPAL or not sub.paypal_subscription_id:
            return Response({"detail": "Not a PayPal subscription"}, status=status.HTTP_400_BAD_REQUEST)

        plan_id = request.data.get("plan_id")
        try:
            new_plan = SubscriptionPlan.objects.get(id=plan_id)
        except SubscriptionPlan.DoesNotExist:
            return Response({"detail": "Invalid plan_id"}, status=status.HTTP_400_BAD_REQUEST)

        if not new_plan.paypal_plan_id:
             return Response({"detail": "New plan not configured for PayPal"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            revise_subscription(sub.paypal_subscription_id, new_plan.paypal_plan_id)
            
            # Update local DB immediately (optimistic) or wait for webhook
            sub.plan = new_plan
            sub.save()
            
            return Response({"detail": "Subscription updated successfully"}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

class CancelPayPalSubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            shop = request.user.shop
            sub = shop.subscription
        except (Shop.DoesNotExist, ShopSubscription.DoesNotExist):
             return Response({"detail": "Subscription not found"}, status=status.HTTP_404_NOT_FOUND)

        if sub.provider != ShopSubscription.PROVIDER_PAYPAL or not sub.paypal_subscription_id:
            return Response({"detail": "Not a PayPal subscription"}, status=status.HTTP_400_BAD_REQUEST)

        reason = request.data.get("reason", "User requested cancellation")
        
        if cancel_subscription(sub.paypal_subscription_id, reason=reason):
            sub.status = "canceled"
            sub.paypal_subscription_id = None
            sub.provider = None
            # Downgrade to Foundation
            try:
                foundation = SubscriptionPlan.objects.get(name=SubscriptionPlan.FOUNDATION)
                sub.plan = foundation
            except SubscriptionPlan.DoesNotExist:
                sub.plan = None
            sub.save()
            return Response({"detail": "Subscription canceled successfully"}, status=status.HTTP_200_OK)
        
        return Response({"detail": "Failed to cancel subscription"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

class CreatePayPalAiAddonView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Body: { "plan_id": <SubscriptionPlan.id> } // AI add-on plan
        """
        try:
            shop = request.user.shop
        except Shop.DoesNotExist:
            return Response({"detail": "Shop not found"}, status=status.HTTP_404_NOT_FOUND)

        plan_id = request.data.get("plan_id")

        try:
            plan = SubscriptionPlan.objects.get(id=plan_id)
        except SubscriptionPlan.DoesNotExist:
            return Response({"detail": "Invalid plan_id"}, status=status.HTTP_400_BAD_REQUEST)

        if not plan.paypal_plan_id:
            return Response(
                {"detail": "AI add-on plan is not configured for PayPal"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return_url = request.build_absolute_uri(reverse("paypal_return"))
        cancel_url = request.build_absolute_uri(reverse("paypal_cancel"))

        try:
            paypal_sub_id, approval_url = create_subscription(plan, shop, return_url, cancel_url)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        sub, _ = ShopSubscription.objects.get_or_create(shop=shop)
        sub.ai_provider = ShopSubscription.PROVIDER_PAYPAL
        sub.ai_paypal_subscription_id = paypal_sub_id
        sub.ai_addon_active = False  # wait until webhook
        sub.save()

        return Response(
            {
                "approval_url": approval_url,
                "subscription_id": paypal_sub_id,
            },
            status=status.HTTP_200_OK,
        )

class CancelPayPalAiAddonView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            shop = request.user.shop
            sub = shop.subscription
        except (Shop.DoesNotExist, ShopSubscription.DoesNotExist):
             return Response({"detail": "Subscription not found"}, status=status.HTTP_404_NOT_FOUND)

        if sub.ai_provider != ShopSubscription.PROVIDER_PAYPAL or not sub.ai_paypal_subscription_id:
            return Response({"detail": "Not a PayPal AI add-on"}, status=status.HTTP_400_BAD_REQUEST)

        reason = request.data.get("reason", "User requested cancellation of AI add-on")
        
        if cancel_subscription(sub.ai_paypal_subscription_id, reason=reason):
            sub.ai_addon_active = False
            sub.ai_paypal_subscription_id = None
            sub.ai_provider = None
            sub.save()
            return Response({"detail": "AI add-on canceled successfully"}, status=status.HTTP_200_OK)
        
        return Response({"detail": "Failed to cancel AI add-on"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

class PayPalReturnView(View):
    def get(self, request):
        # PayPal redirects here with token=...
        # We can just deep link back to the app, similar to Stripe
        deeplink = f"{APP_SCHEME}://subscription/success" 
        return HttpResponse(_HTML % {"deeplink": deeplink})

class PayPalCancelView(View):
    def get(self, request):
        deeplink = f"{APP_SCHEME}://subscription/cancel"
        return HttpResponse(_HTML % {"deeplink": deeplink})

