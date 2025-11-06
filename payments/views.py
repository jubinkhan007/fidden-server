# payments/views.py

import os
import requests
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import stripe
from api.utils.zapier import send_klaviyo_event
import logging
from decimal import Decimal
import json
from datetime import timedelta, datetime
from django.utils.timezone import now
from django.conf import settings
from rest_framework.exceptions import ValidationError
from api.models import Shop, Coupon
from api.serializers import SlotBookingSerializer, CouponSerializer
from accounts.models import User
from api.utils.slots import assert_slot_bookable
from payments.utils.emitters import emit_subscription_updated_to_zapier
from .models import Payment, UserStripeCustomer, Booking, TransactionLog, CouponUsage, can_use_coupon
from subscriptions.models import SubscriptionPlan, ShopSubscription
from .serializers import userBookingSerializer, ownerBookingSerializer, TransactionLogSerializer, ApplyCouponSerializer
from .pagination import BookingCursorPagination, TransactionCursorPagination
from .utils.helper_function import extract_validation_error_message
from django.http import HttpResponse, HttpResponseRedirect
from urllib.parse import urlencode, urljoin
# views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from api.models import Slot
from api.serializers import SlotSerializer
from django.db import DatabaseError, transaction
from dateutil.relativedelta import relativedelta
from django.utils import timezone
import datetime


logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY
STRIPE_ENDPOINT_SECRET = settings.STRIPE_ENDPOINT_SECRET

# paymetns/views.py
def _update_shop_from_subscription_obj(sub_obj, shop_hint=None):
    """
    Persist the plan + period window from Stripe, then emit one Zapier event.
    Assumes you call this from *one* webhook path (e.g., checkout.session.completed) or
    you let cache idempotency suppress duplicates.
    """
    # Ensure expanded subscription
    if isinstance(sub_obj, dict):
        sub_id = sub_obj.get("id")
    else:
        sub_id = sub_obj.id

    # Fully expand to avoid the ListObject indexing error you saw
    sub = stripe.Subscription.retrieve(
        sub_id,
        expand=[
            "items.data.price",
            "latest_invoice.payment_intent",
            "latest_invoice.charge",
            "latest_invoice.lines.data.period",
        ],
    )

    items = (sub.get("items") or {}).get("data") or []
    if not items:
        logger.error("Subscription %s has no items; cannot map plan", sub_id)
        return

    price_id = ((items[0] or {}).get("price") or {}).get("id")
    try:
        new_plan = SubscriptionPlan.objects.get(stripe_price_id=price_id)
    except SubscriptionPlan.DoesNotExist:
        logger.error("No SubscriptionPlan with stripe_price_id=%s", price_id)
        return

    # Resolve shop (your existing logic) -> shop
    shop = shop_hint  # implement/keep your resolver
    if not shop:
        logger.error("Cannot resolve shop for subscription %s", sub_id)
        return

    # --- capture previous plan before overwriting ---
    prev_sub = ShopSubscription.objects.filter(shop=shop).first()
    previous_plan_name = prev_sub.plan.name if (prev_sub and prev_sub.plan) else None

    # --- persist the new plan/window (your existing write) ---
    # example:
    ss, _ = ShopSubscription.objects.get_or_create(shop=shop)
    ss.plan = new_plan
    ss.start_date = datetime.fromtimestamp(int(sub["current_period_start"]), tz=timezone.utc)
    ss.end_date   = datetime.fromtimestamp(int(sub["current_period_end"]),   tz=timezone.utc)
    ss.status = "active" if sub.get("status") == "active" else sub.get("status")
    ss.stripe_subscription_id = sub_id
    ss.save()

    # --- only now: emit ONE event with full context ---
    emit_subscription_updated_to_zapier(
        sub=sub,
        shop=shop,
        previous_plan_name=previous_plan_name,
        current_plan_name=new_plan.name,
        extra_fields={"shop_name": getattr(shop, "name", None)},  # <- added
    )





class CreatePaymentIntentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, slot_id):
        user = request.user
        coupon_id = request.data.get("coupon_id")
        coupon = None
        discount = 0.0

        # 1) Validate & attach coupon (optional)
        coupon_serializer = None
        if coupon_id:
            coupon_serializer = ApplyCouponSerializer(
                data={"coupon_id": coupon_id},
                context={"request": request},
            )
            try:
                coupon_serializer.is_valid(raise_exception=True)
                coupon = coupon_serializer.coupon
            except ValidationError as e:
                return Response(
                    {"detail": extract_validation_error_message(e)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # ─────────────────────────────────────────────────────────────
        # 2) ATOMIC BLOCK: lock slot, re-check, and create the Booking
        #    (release the lock as soon as we have a booking)
        # ─────────────────────────────────────────────────────────────
        try:
            with transaction.atomic():
                # lock the specific slot row for concurrency safety
                slot = (
                    Slot.objects
                    .select_for_update()
                    .select_related("service", "service__shop")
                    .filter(id=slot_id)
                    .first()
                )
                if not slot:
                    return Response({"detail": "Slot not found."}, status=status.HTTP_404_NOT_FOUND)

                # hard guard (future, capacity, disabled times, etc.)
                try:
                    assert_slot_bookable(slot)
                except ValidationError as e:
                    return Response(
                        {"detail": str(e.detail[0] if isinstance(e.detail, list) else e.detail)},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # create the booking while the slot is locked
                serializer = SlotBookingSerializer(
                    data={"slot_id": slot_id},
                    context={"request": request},
                )
                serializer.is_valid(raise_exception=True)
                booking = serializer.save()
        except DatabaseError as e:
            logger.exception("DB error while locking/booking slot %s: %s", slot_id, e)
            return Response({"detail": "Could not reserve this slot. Please try another time."},
                            status=status.HTTP_409_CONFLICT)
        # ─────────── lock released here ───────────

        try:
            # 3) Ensure Stripe Customer for user
            user_customer, _ = UserStripeCustomer.objects.get_or_create(user=user)
            if not user_customer.stripe_customer_id:
                sc = stripe.Customer.create(email=user.email)
                user_customer.stripe_customer_id = sc.id
                user_customer.save(update_fields=["stripe_customer_id"])

            # 4) Require shop’s Stripe Connect account (destination)
            shop = booking.shop
            shop_account = getattr(shop, "stripe_account", None)
            if not shop_account or not shop_account.stripe_account_id:
                return Response(
                    {"detail": "Shop Stripe account not found"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 5) Resolve a plan for commission (do NOT gate booking)
            shop_subscription = getattr(shop, "subscription", None)
            plan = getattr(shop_subscription, "plan", None)
            if not plan:
                try:
                    plan = (
                        SubscriptionPlan.objects.filter(name=SubscriptionPlan.FOUNDATION).first()
                        or SubscriptionPlan.objects.order_by("id").first()
                    )
                except Exception:
                    plan = None
                if not shop_subscription and plan:
                    ShopSubscription.objects.update_or_create(
                        shop=shop,
                        defaults={
                            "plan": plan,
                            "status": ShopSubscription.STATUS_ACTIVE,
                            "start_date": timezone.now(),
                            "end_date": timezone.now() + relativedelta(years=100),
                            "stripe_subscription_id": None,
                        },
                    )
                    shop_subscription = getattr(shop, "subscription", None)

            # 6) Price (consider discount price), then deposit logic
            total_amount = (
                booking.service.discount_price
                if booking.service.discount_price > 0
                else booking.service.price
            )
            full_service_amount = total_amount

            if shop.is_deposit_required:
                service = booking.service
                deposit_amount = service.deposit_amount if service.deposit_amount else full_service_amount
                total_amount = min(deposit_amount, full_service_amount)
            else:
                deposit_amount = full_service_amount

            remaining_balance = (
                full_service_amount - total_amount if shop.is_deposit_required else Decimal("0.00")
            )
            total_amount = float(total_amount)

            # 7) Apply coupon (after deposit calc)
            if coupon:
                if coupon.in_percentage:
                    discount = (total_amount * float(coupon.amount)) / 100.0
                else:
                    discount = float(coupon.amount)
                total_amount = max(total_amount - discount, 0.0)
                # record usage only after successful validation
                coupon_serializer.create_usage()

            # 8) Compute application fee (commission)
            try:
                commission_rate = float(plan.commission_rate) if plan and plan.commission_rate is not None else 0.0
            except Exception:
                commission_rate = 0.0
            application_fee_cents = 0
            if commission_rate > 0:
                commission = (total_amount * commission_rate) / 100.0
                application_fee_cents = int(round(commission * 100))

            # 9) Create PaymentIntent (Connect destination charges)
            amount_cents = int(round(total_amount * 100))
            payment_intent_params = {
                "amount": amount_cents,
                "currency": "usd",
                "customer": user_customer.stripe_customer_id,
                "payment_method_types": ["card"],
                "transfer_data": {"destination": shop_account.stripe_account_id},
                "metadata": {"booking_id": booking.id},
            }
            if application_fee_cents > 0:
                payment_intent_params["application_fee_amount"] = application_fee_cents

            intent = stripe.PaymentIntent.create(**payment_intent_params)

            # 10) Persist Payment row (small atomic to keep consistency)
            with transaction.atomic():
                Payment.objects.update_or_create(
                    booking=booking,
                    defaults={
                        "user": user,
                        "amount": total_amount,
                        "total_amount": total_amount,
                        "coupon": coupon,
                        "coupon_amount": discount if coupon else None,
                        "stripe_payment_intent_id": intent.id,
                        "status": "pending",
                        "is_deposit": shop.is_deposit_required,
                        "balance_paid": 0,
                        "deposit_amount": deposit_amount if shop.is_deposit_required else 0,
                        "remaining_amount": remaining_balance,
                        "deposit_paid": 0,
                        "tips_amount": 0,
                        "application_fee_amount": 0,
                        "payment_type": "full",
                    },
                )

            # 11) Ephemeral key for mobile SDKs
            ephemeral_key = stripe.EphemeralKey.create(
                customer=user_customer.stripe_customer_id,
                stripe_version="2024-04-10",
            )

            return Response(
                {
                    "booking_id": booking.id,
                    "client_secret": intent.client_secret,
                    "payment_intent_id": intent.id,
                    "ephemeral_key": ephemeral_key.secret,
                    "customer_id": user_customer.stripe_customer_id,
                    "coupon_applied": bool(coupon),
                    "shop_plan": getattr(plan, "name", None),
                    "application_fee_cents": application_fee_cents,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            import traceback
            logger.error(f"Payment creation failed: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


APP_SCHEME = getattr(settings, "APP_URL_SCHEME", "myapp")
APP_HOST   = getattr(settings, "APP_URL_HOST",   "stripe")

class StripeReturnView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        qp = request.GET.dict()
        qp.setdefault("result", "success")
        deeplink = f"{APP_SCHEME}://{APP_HOST}/return?{urlencode(qp)}"
        resp = HttpResponse(status=302)
        resp["Location"] = deeplink
        return resp


class StripeRefreshView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        qp = request.GET.dict()
        qp.setdefault("result", "refresh")
        deeplink = f"{APP_SCHEME}://{APP_HOST}/refresh?{urlencode(qp)}"
        resp = HttpResponse(status=302)
        resp["Location"] = deeplink
        return resp




class ShopSlotsView(APIView):
    def get(self, request, shop_id):
        service_id = request.query_params.get('service')
        date_str   = request.query_params.get('date')  # YYYY-MM-DD

        qs = (Slot.objects
              .filter(shop_id=shop_id, service_id=service_id, start_time__date=date_str)
              .select_related('service', 'service__shop')
              .prefetch_related('service__disabled_times'))

        data = SlotSerializer(qs, many=True, context={'request': request}).data
        return Response({'slots': data})



class ShopOnboardingLinkView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, shop_id):
        print("[onboarding] v2 view active")
        shop = get_object_or_404(Shop, id=shop_id)
        user = request.user
        if getattr(user, "role", None) != "owner":
            return Response({"detail": "Only owner can view services."}, status=status.HTTP_403_FORBIDDEN)

        if not hasattr(shop, "stripe_account") or not shop.stripe_account.stripe_account_id:
            return Response({"detail": "Shop Stripe account not found"}, status=status.HTTP_400_BAD_REQUEST)

        base_url = getattr(settings, "BASE_URL", "https://yourdomain.com").rstrip("/")
        # build HTTPS callbacks that Stripe accepts
        default_return  = urljoin(base_url + "/", "payments/stripe/return/")
        default_refresh = urljoin(base_url + "/", "payments/stripe/refresh/")

        # allow optional overrides (?return_url=...&refresh_url=...) – must be HTTPS
        return_url  = request.query_params.get("return_url",  default_return)
        refresh_url = request.query_params.get("refresh_url", default_refresh)

        # Hard-check: reject non-HTTPS to avoid “Not a valid URL”
        if not (return_url.startswith("https://") and refresh_url.startswith("https://")):
            return Response({"detail":"return_url and refresh_url must be https URLs"}, status=400)

        account_link = stripe.AccountLink.create(
            account=shop.stripe_account.stripe_account_id,
            refresh_url=refresh_url,
            return_url=return_url,
            type="account_onboarding",
        )
        return Response({"url": account_link.url})

class SaveCardView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        user_customer, _ = UserStripeCustomer.objects.get_or_create(user=user)

        if not user_customer.stripe_customer_id:
            stripe_customer = stripe.Customer.create(email=user.email)
            user_customer.stripe_customer_id = stripe_customer.id
            user_customer.save()

        # Create SetupIntent to save card
        setup_intent = stripe.SetupIntent.create(
            customer=user_customer.stripe_customer_id,
            payment_method_types=["card"],
        )

        return Response({"client_secret": setup_intent.client_secret}, status=200)


# --- helpers for Klaviyo profile + status normalization ---

def normalize_plan_status(
    *,
    sub_status: str | None,
    cancel_at_period_end: bool = False,
    is_canceled: bool = False,
    is_at_risk: bool = False,
) -> str:
    """
    Force plan_status to one of:
    'active' | 'trialing' | 'scheduled_cancel' | 'canceled' | 'at_risk'
    """
    if is_at_risk:
        return "at_risk"
    if is_canceled:
        return "canceled"
    if cancel_at_period_end:
        return "scheduled_cancel"

    # default mapping from our ShopSubscription.status / Stripe status
    s = (sub_status or "").lower()
    # common values we might see internally:
    #   "active", "trialing", "canceled", "inactive", etc.
    if "trial" in s:
        return "trialing"
    if "active" in s:
        return "active"

    # fallback
    return "active"


import decimal

def convert_decimal(obj):
    if isinstance(obj, dict):
        return {k: convert_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimal(i) for i in obj]
    elif isinstance(obj, decimal.Decimal):
        return float(obj)
    else:
        return obj


def build_profile_payload_for_shop(
    *,
    shop,
    shop_sub,
    stripe_subscription_id: str | None,
    price_id: str | None,
    cancel_at_period_end: bool = False,
    is_canceled: bool = False,
    is_at_risk: bool = False,
) -> dict:
    """
    Central place to shape the profile dict we send to Zapier/Klaviyo.
    This enforces the normalized plan_status contract.
    """

    owner = getattr(shop, "owner", None)
    stripe_customer_id = getattr(
        getattr(owner, "stripe_customer", None),
        "stripe_customer_id",
        None,
    )

    # end_date in ShopSubscription = next billing date / period end
    next_billing_iso = (
        shop_sub.end_date.isoformat()
        if getattr(shop_sub, "end_date", None)
        else None
    )

    # if "trialing", spec wants trial_end also
    trial_end = (
        shop_sub.end_date.isoformat()
        if normalize_plan_status(
            sub_status=getattr(shop_sub, "status", None),
            cancel_at_period_end=cancel_at_period_end,
            is_canceled=is_canceled,
            is_at_risk=is_at_risk,
        )
        == "trialing"
        else None
    )

    return {
        "plan": getattr(getattr(shop_sub, "plan", None), "name", None),
        "plan_status": normalize_plan_status(
            sub_status=getattr(shop_sub, "status", None),
            cancel_at_period_end=cancel_at_period_end,
            is_canceled=is_canceled,
            is_at_risk=is_at_risk,
        ),
        "ai_addon": bool(getattr(shop_sub, "has_ai_addon", False)),
        "legacy_500": bool(getattr(shop_sub, "legacy_ai_promo_used", False)),
        "next_billing_date": next_billing_iso,
        "trial_end": trial_end,
        "stripe_customer_id": stripe_customer_id,
        "stripe_subscription_id": stripe_subscription_id,
        "price_id": price_id,
        "shop_id": getattr(shop, "id", None),
    }

# payments/views.py
@method_decorator(csrf_exempt, name="dispatch")
class StripeWebhookView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request, *args, **kwargs):
        payload = request.body
        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
        logger.info("=" * 80)
        logger.info("🔔 WEBHOOK RECEIVED at %s", timezone.now())
        logger.info("Signature present: %s", bool(sig_header))
        logger.info("=" * 80)

        # 1. Verify Stripe signature
        try:
            event = stripe.Webhook.construct_event(
                payload,
                sig_header,
                settings.STRIPE_ENDPOINT_SECRET
            )
            logger.info(" Webhook signature verified")
        except ValueError as e:
            logger.error("❌ Invalid payload: %s", str(e))
            return Response({"error": "Invalid payload"}, status=400)
        except stripe.error.SignatureVerificationError as e:
            logger.error("❌ Invalid signature: %s", str(e))
            return Response({"error": "Invalid signature"}, status=400)

        event_type = event["type"]
        data = event["data"]["object"]

        logger.info(
            "📨 Event: %s (livemode=%s, id=%s)",
            event_type,
            bool(event.get("livemode")),
            event.get("id")
        )

        # ------------------------------------------------------------------
        # Payment-related events
        # ------------------------------------------------------------------
        # Subscription created or updated
        if event_type in ("customer.subscription.created", "customer.subscription.updated"):
            self.handle_subscription_created_or_updated(data)
            return Response(status=200)

        # Payment succeeded
        elif event_type == "payment_intent.succeeded":
            self._update_payment_status(data, "succeeded")
            return Response(status=200)

        # Handle AI add-on and other events
        elif event_type == "checkout.session.completed":
            self.handle_checkout_session_completed(data)
            return Response(status=200)
        elif event_type == "payment_intent.payment_failed":
            self._update_payment_status(data, "failed")
            return Response(status=200)
        elif event_type == "payment_intent.canceled":
            self._update_payment_status(data, "cancelled")
            return Response(status=200)
        elif event_type == "charge.succeeded":
            self._update_payment_status(data, "succeeded")
            return Response(status=200)
        elif event_type == "charge.failed":
            self._update_payment_status(data, "failed")
            return Response(status=200)

        # ------------------------------------------------------------------
        # Transfer events (Connect payouts etc.)
        # ------------------------------------------------------------------
        if event_type.startswith("transfer."):
            logger.info("Transfer event: %s %s", event_type, data.get("id"))
            return Response(status=200)

        # ------------------------------------------------------------------
        # checkout.session.completed
        # - customer just purchased a plan or add-on through Checkout
        # ------------------------------------------------------------------
        # if event_type == "checkout.session.completed":
        #     session = data
        #     shop_ref = session.get("client_reference_id")
        #     sub_id = session.get("subscription")

        #     shop_hint = None
        #     if shop_ref:
        #         try:
        #             shop_hint = Shop.objects.get(id=int(shop_ref))
        #             logger.info("[checkout] resolved shop_hint=%s", shop_hint.id)
        #         except Exception:
        #             logger.warning("[checkout] bad client_reference_id: %r", shop_ref)

        #     if sub_id:
        #         sub = stripe.Subscription.retrieve(
        #             sub_id,
        #             expand=["items.data.price", "latest_invoice.payment_intent"]
        #         )
        #         sub_meta = sub.get("metadata") or {}

        #         # ensure subscription.metadata.shop_id is set in Stripe for future webhooks
        #         # make sure Stripe sub.metadata.shop_id is set
        #         if shop_hint:
        #             try:
        #                 if str(sub_meta.get("shop_id")) != str(shop_hint.id):
        #                     stripe.Subscription.modify(
        #                         sub["id"],
        #                         metadata={**sub_meta, "shop_id": str(shop_hint.id)}
        #                     )
        #             except Exception:
        #                 logger.exception("Failed to set subscription metadata.shop_id")

        #         price_ids = [
        #             it["price"]["id"]
        #             for it in (sub.get("items", {}).get("data") or [])
        #         ]
        #         ai_price_id = getattr(settings, "STRIPE_AI_PRICE_ID", None)
        #         is_ai_addon = (
        #             sub_meta.get("addon") == "ai_assistant"
        #             or (ai_price_id and ai_price_id in price_ids)
        #         )

        #         if is_ai_addon:
        #             # Mark AI add-on active and legacy promo if applicable
        #             if shop_hint and hasattr(shop_hint, "subscription"):
        #                 ss = shop_hint.subscription
        #                 ss.has_ai_addon = True
        #                 ss.ai_subscription_id = sub["id"]

        #                 ai_item = next(
        #                     (
        #                         it
        #                         for it in (sub.get("items", {}).get("data") or [])
        #                         if (it.get("price") or {}).get("id") == ai_price_id
        #                     ),
        #                     None,
        #                 )
        #                 ss.ai_subscription_item_id = (
        #                     ai_item.get("id") if ai_item else None
        #                 )

        #                 # Check invoice discounts for legacy promo
        #                 try:
        #                     inv = sub.get("latest_invoice")
        #                     if isinstance(inv, str):
        #                         inv = stripe.Invoice.retrieve(
        #                             inv,
        #                             expand=[
        #                                 "discounts",
        #                                 "discounts.discount.coupon",
        #                             ],
        #                         )
        #                     discounts = inv.get("discounts", []) if inv else []
        #                     if any(
        #                         d.get("discount", {})
        #                         .get("coupon", {})
        #                         .get("id")
        #                         == settings.STRIPE_LEGACY_COUPON_ID
        #                         for d in discounts
        #                     ):
        #                         ss.legacy_ai_promo_used = True
        #                         logger.info(
        #                             "✅ LEGACY promo applied for shop %s",
        #                             shop_hint.id,
        #                         )
        #                 except Exception:
        #                     logger.exception("Promo detection failed")
                        
        #                 try:
        #                     owner = shop_hint.owner  # or ss.shop.owner if you have `shop_hint`
        #                     email = getattr(owner, "email", None)

        #                     if email:
        #                         profile_payload = build_profile_payload_for_shop(
        #                             shop=ss.shop,
        #                             shop_sub=ss,
        #                             stripe_subscription_id=ss.ai_subscription_id or ss.stripe_subscription_id,
        #                             price_id=None,
        #                             cancel_at_period_end=False,
        #                             is_canceled=False,
        #                             is_at_risk=False,
        #                         )
        #                         # Force ai_addon / legacy_500 to reflect the new state (in case builder didn't yet see it)
        #                         profile_payload["ai_addon"] = True
        #                         profile_payload["legacy_500"] = bool(ss.legacy_ai_promo_used)

        #                         event_props = {
        #                             "shop_id": ss.shop.id,
        #                             "legacy_500": bool(ss.legacy_ai_promo_used),
        #                         }

        #                         send_klaviyo_event(
        #                             email=email,
        #                             event_name="AI Addon Started",
        #                             profile=profile_payload,
        #                             event_props=event_props,
        #                         )
        #                 except Exception as e:
        #                     logger.error("[klaviyo] AI addon start sync failed: %s", e, exc_info=True)

        #                 ss.save(
        #                     update_fields=[
        #                         "has_ai_addon",
        #                         "ai_subscription_id",
        #                         "ai_subscription_item_id",
        #                         "legacy_ai_promo_used",
        #                     ]
        #                 )
        #                 logger.info(
        #                     "✅ AI Assistant add-on enabled for shop %s",
        #                     shop_hint.id,
        #                 )
        #             return Response(status=200)
                
        #         # non-AI plan changes
        #         _update_shop_from_subscription_obj(sub)
        #         return Response(status=200)

        #     return Response(status=200)

        # ------------------------------------------------------------------
        # customer.subscription.created / updated
        # - Subscription lifecycle events from Stripe
        # ------------------------------------------------------------------
        if event_type in (
            "customer.subscription.created",
            "customer.subscription.updated",
        ):
            sub = data
            ai_price_id = getattr(settings, "STRIPE_AI_PRICE_ID", None)
            price_ids = [
                it["price"]["id"]
                for it in (sub.get("items", {}).get("data") or [])
            ]
            is_ai_addon = (
                sub.get("metadata", {}).get("addon") == "ai_assistant"
                or (ai_price_id and ai_price_id in price_ids)
            )

            if is_ai_addon:
                shop = None
                sid = (sub.get("metadata") or {}).get("shop_id")
                if sid:
                    try:
                        shop = Shop.objects.get(id=int(sid))
                    except Exception:
                        shop = None
                if not shop:
                    ss = (
                        ShopSubscription.objects.filter(
                            stripe_subscription_id=sub["id"]
                        )
                        .select_related("shop")
                        .first()
                    )
                    if ss:
                        shop = ss.shop

                if shop and hasattr(shop, "subscription"):
                    ss = shop.subscription
                    ss.has_ai_addon = True
                    ss.ai_subscription_id = sub["id"]

                    ai_item = next(
                        (
                            it
                            for it in (sub.get("items", {}).get("data") or [])
                            if (it.get("price") or {}).get("id") == ai_price_id
                        ),
                        None,
                    )
                    ss.ai_subscription_item_id = (
                        ai_item.get("id") if ai_item else None
                    )
                    ss.save(
                        update_fields=[
                            "has_ai_addon",
                            "ai_subscription_id",
                            "ai_subscription_item_id",
                        ]
                    )
                return Response(status=200)

            # non-AI plan changes
            _update_shop_from_subscription_obj(sub)
            # ---- NEW: fire Klaviyo profile/event for scheduled cancel info ----
            try:
                # figure out which shop this sub belongs to (same logic as _update_shop_from_subscription_obj, but we repeat minimal bits)
                target_shop = None
                meta = sub.get("metadata") or {}
                sid = meta.get("shop_id")
                if sid:
                    try:
                        target_shop = Shop.objects.get(id=int(sid))
                    except Exception:
                        target_shop = None
                if not target_shop:
                    tmp_ss = (
                        ShopSubscription.objects
                        .filter(stripe_subscription_id=sub["id"])
                        .select_related("shop","plan")
                        .first()
                    )
                    if tmp_ss:
                        target_shop = tmp_ss.shop

                if target_shop and hasattr(target_shop, "subscription"):
                    ss = target_shop.subscription
                    owner = target_shop.owner
                    email = getattr(owner, "email", None)

                    if email:
                        profile_payload = build_profile_payload_for_shop(
                            shop=target_shop,
                            shop_sub=ss,
                            stripe_subscription_id=sub.get("id"),
                            price_id=(
                                # grab first price_id from sub.items
                                (sub.get("items", {}) or {})
                                    .get("data", [{}])[0]
                                    .get("price", {})
                                    .get("id")
                            ),
                            cancel_at_period_end=bool(sub.get("cancel_at_period_end")),
                            is_canceled=False,
                            is_at_risk=False,
                        )

                        event_props = {
                            "shop_id": target_shop.id,
                            "status": profile_payload["plan_status"],
                            "cancel_at_period_end": bool(sub.get("cancel_at_period_end")),
                        }

                        self.send_klaviyo_event(
                            email=email,
                            event_name="Subscription Updated",
                            profile=profile_payload,
                            event_props=event_props,
                        )

            except Exception as e:
                logger.error("[klaviyo] sub.updated Klaviyo sync failed: %s", e, exc_info=True)

            return Response(status=200)
        # ------------------------------------------------------------------
        # invoice.* (paid / succeeded etc.)
        # - Recurring billing events
        # ------------------------------------------------------------------
        if event_type in (
            "invoice.payment_succeeded",
            "invoice.paid",
            "invoice_payment.paid",
        ):
            sub_id = data.get("subscription")
            if sub_id:
                try:
                    sub = stripe.Subscription.retrieve(
                        sub_id, expand=["items.data.price"]
                    )

                    ai_price_id = getattr(settings, "STRIPE_AI_PRICE_ID", None)
                    price_ids = [
                        it["price"]["id"]
                        for it in (sub.get("items", {}).get("data") or [])
                    ]

                    # AI add-on renewal
                    if (
                        sub.get("metadata", {}).get("addon")
                        == "ai_assistant"
                    ) or (ai_price_id and ai_price_id in price_ids):
                        # mark add-on active
                        shop = None
                        meta = sub.get("metadata") or {}
                        sid = meta.get("shop_id")
                        if sid:
                            try:
                                shop = Shop.objects.get(id=int(sid))
                            except Exception:
                                shop = None
                        if not shop:
                            ss = (
                                ShopSubscription.objects.filter(
                                    stripe_subscription_id=sub["id"]
                                )
                                .select_related("shop")
                                .first()
                            )
                            if ss:
                                shop = ss.shop
                        if shop and hasattr(shop, "subscription"):
                            shop.subscription.has_ai_addon = True
                            shop.subscription.save(
                                update_fields=["has_ai_addon"]
                            )
                            logger.info(
                                "(invoice.*) AI add-on active for shop %s",
                                shop.id,
                            )
                        return Response(status=200)

                    # normal plan invoice paid
                    _update_shop_from_subscription_obj(sub)
                except Exception as e:
                    logger.exception(
                        "invoice handler failed for %s: %s", sub_id, e
                    )
            return Response(status=200)

        # ------------------------------------------------------------------
        # customer.subscription.deleted
        # - Merchant cancelled or subscription ended
        # ------------------------------------------------------------------
        if event_type == "customer.subscription.deleted":
            stripe_sub = data  # Stripe subscription object that ended

            ai_price_id = getattr(settings, "STRIPE_AI_PRICE_ID", None)
            price_ids = [
                it.get("price", {}).get("id")
                for it in (stripe_sub.get("items", {}).get("data") or [])
            ]
            is_ai_addon = (
                (stripe_sub.get("metadata", {}) or {}).get("addon") == "ai_assistant"
                or (ai_price_id and ai_price_id in price_ids)
            )

            # Try to locate the ShopSubscription row for this subscription
            shop_sub = (
                ShopSubscription.objects
                .filter(stripe_subscription_id=stripe_sub.get("id"))
                .select_related("shop", "plan")
                .first()
            )

            if is_ai_addon:
                # AI add-on was cancelled
                if shop_sub:
                    ss = shop_sub
                else:
                    # fallback: try to infer shop via metadata.shop_id
                    ss = None
                    sid = (stripe_sub.get("metadata") or {}).get("shop_id")
                    if sid:
                        try:
                            shop = Shop.objects.get(id=int(sid))
                            ss = getattr(shop, "subscription", None)
                        except Exception:
                            ss = None

                if ss:
                    # turn off AI flags
                    ss.has_ai_addon = False
                    ss.ai_subscription_id = None
                    ss.ai_subscription_item_id = None
                    ss.save(update_fields=["has_ai_addon", "ai_subscription_id", "ai_subscription_item_id"])

                    # send Klaviyo "AI Addon Canceled"
                    owner = ss.shop.owner
                    email = getattr(owner, "email", None)
                    if email:
                        profile_payload = build_profile_payload_for_shop(
                            shop=ss.shop,
                            shop_sub=ss,
                            stripe_subscription_id=getattr(ss, "stripe_subscription_id", None),
                            price_id=getattr(getattr(ss, "plan", None), "stripe_price_id", None)
                                if hasattr(ss, "plan") else None,
                            cancel_at_period_end=False,
                            is_canceled=False,   # base plan might still be active
                            is_at_risk=False,
                        )

                        event_props = {
                            "shop_id": ss.shop.id,
                            "reason": "ai_addon_cancelled",
                        }

                        self.send_klaviyo_event(
                            email=email,
                            event_name="AI Addon Canceled",
                            profile=profile_payload,
                            event_props=event_props,
                        )

                return Response(status=200)

            # ELSE: base subscription canceled → fall back to your existing downgrade logic
            try:
                if shop_sub:
                    # move them to Foundation "forever"
                    try:
                        foundation = SubscriptionPlan.objects.get(name=SubscriptionPlan.FOUNDATION)
                    except SubscriptionPlan.DoesNotExist:
                        foundation = None

                    shop_sub.plan = foundation
                    shop_sub.status = ShopSubscription.STATUS_ACTIVE  # stays usable in app
                    shop_sub.stripe_subscription_id = None
                    shop_sub.end_date = timezone.now() + relativedelta(years=100)
                    shop_sub.save()

                    owner = shop_sub.shop.owner
                    email = getattr(owner, "email", None)

                    if email:
                        # build profile with plan_status="canceled"
                        profile_payload = build_profile_payload_for_shop(
                            shop=shop_sub.shop,
                            shop_sub=shop_sub,
                            stripe_subscription_id=stripe_sub.get("id"),
                            price_id=None,
                            cancel_at_period_end=False,
                            is_canceled=True,
                            is_at_risk=False,
                        )

                        event_props = {
                            "shop_id": shop_sub.shop.id,
                            "shop_name": getattr(shop_sub.shop, "name", None),
                            "previous_plan": getattr(getattr(shop_sub, "plan", None), "name", None),
                            "current_plan": "Canceled",
                            "status": "canceled",
                            "reason": "user_cancelled",
                        }

                        self.send_klaviyo_event(
                            email=email,
                            event_name="Subscription Canceled",
                            profile=profile_payload,
                            event_props=event_props,
                        )
            except Exception as e:
                logger.error("[klaviyo] cancel sync failed: %s", e, exc_info=True)

            return Response(status=200)


        # ------------------------------------------------------------------
        # Fallback
        # ------------------------------------------------------------------
        logger.warning("⚠️ Unhandled event: %s", event_type)
        return Response(status=200)
    
    
    def handle_subscription_created_or_updated(self, data):
        sub = data
        ai_price_id = getattr(settings, "STRIPE_AI_PRICE_ID", None)
        price_ids = [
            it["price"]["id"]
            for it in (sub.get("items", {}).get("data") or [])
        ]
        is_ai_addon = (
            sub.get("metadata", {}).get("addon") == "ai_assistant"
            or (ai_price_id and ai_price_id in price_ids)
        )

        if is_ai_addon:
            shop = None
            sid = (sub.get("metadata") or {}).get("shop_id")
            if sid:
                try:
                    shop = Shop.objects.get(id=int(sid))
                except Exception:
                    shop = None

            if shop and hasattr(shop, "subscription"):
                ss = shop.subscription
                ss.has_ai_addon = True
                ss.ai_subscription_id = sub["id"]

                ai_item = next(
                    (
                        it
                        for it in (sub.get("items", {}).get("data") or [])
                        if (it.get("price") or {}).get("id") == ai_price_id
                    ),
                    None,
                )
                ss.ai_subscription_item_id = (
                    ai_item.get("id") if ai_item else None
                )
                ss.save(
                    update_fields=[
                        "has_ai_addon",
                        "ai_subscription_id",
                        "ai_subscription_item_id",
                    ]
                )

                # Send Klaviyo event
                self.send_klaviyo_event_for_ai_addon_started(shop, ss)

        else:
            _update_shop_from_subscription_obj(sub)

    @staticmethod
    def send_klaviyo_event(*, email, event_name, profile=None, event_props=None, value=None, event_id=None, occurred_at=None):
        payload = {
            "email": email,
            "event_name": event_name,
            "event_id": event_id,
            "value": value,
            "occurred_at": occurred_at,
            "profile": profile or {},
            "event_props": event_props or {},
        }

        # Convert Decimal to float in the payload
        payload = convert_decimal(payload)

        requests.post(settings.ZAPIER_KLAVIYO_WEBHOOK, json=payload, timeout=10)

    def handle_checkout_session_completed(self, data):
        session = data
        shop_ref = session.get("client_reference_id")
        sub_id = session.get("subscription")

        if sub_id:
            sub = stripe.Subscription.retrieve(
                sub_id,
                expand=["items.data.price", "latest_invoice.payment_intent"]
            )
            sub_meta = sub.get("metadata") or {}
            shop_hint = None

            if shop_ref:
                try:
                    shop_hint = Shop.objects.get(id=int(shop_ref))
                    logger.info("[checkout] resolved shop_hint=%s", shop_hint.id)
                except Exception:
                    logger.warning("[checkout] bad client_reference_id: %r", shop_ref)

            if shop_hint:
                self.send_klaviyo_event_for_subscription_purchased(shop_hint, sub, sub_meta)

    def send_klaviyo_event_for_ai_addon_started(self, shop, ss):
        email = shop.owner.email
        profile_payload = build_profile_payload_for_shop(
            shop=shop,
            shop_sub=ss,
            stripe_subscription_id=ss.ai_subscription_id,
            price_id=None,
            cancel_at_period_end=False,
            is_canceled=False,
            is_at_risk=False,
        )
        event_props = {
            "shop_id": ss.shop.id,
            "legacy_500": bool(ss.legacy_ai_promo_used),
        }

        self.send_klaviyo_event(
            email=email,
            event_name="AI Addon Started",
            profile=profile_payload,
            event_props=event_props,
        )

    def send_klaviyo_event_for_subscription_purchased(self, shop_hint, sub, sub_meta):
        target_shop = None
        try:
            # Ensure that the shop is being correctly resolved
            if shop_hint:
                target_shop = shop_hint
            else:
                sid = sub_meta.get("shop_id")
                if sid:
                    try:
                        target_shop = Shop.objects.get(id=int(sid))
                    except Shop.DoesNotExist:
                        logger.error("Shop not found for shop_id: %s", sid)
                        target_shop = None

            # Handle case where no valid shop is found
            if not target_shop:
                logger.error("No valid shop found for subscription ID %s", sub.get("id"))
                return

            # Proceed if we have a valid shop
            email = getattr(target_shop.owner, "email", None)
            if not email:
                logger.error("No email found for shop owner")
                return

            # The rest of your logic here...
            profile_payload = build_profile_payload_for_shop(
                shop=target_shop,
                shop_sub=target_shop.subscription,
                stripe_subscription_id=sub.get("id"),
                price_id=sub.get("items").data[0].get("price").get("id"),
                cancel_at_period_end=False,
                is_canceled=False,
                is_at_risk=False,
            )

            event_props = {
                "shop_id": target_shop.id,
                "status": profile_payload["plan_status"],
                "cancel_at_period_end": bool(sub.get("cancel_at_period_end")),
            }

            self.send_klaviyo_event(
                email=email,
                event_name="Subscription Updated",
                profile=profile_payload,
                event_props=event_props,
            )

        except Exception as e:
            logger.error("[klaviyo] purchase sync failed for shop %s: %s", target_shop.id if target_shop else "N/A", e, exc_info=True)


    # ---------------------------------
    # helper on the view (unchanged)
    # ---------------------------------
    def _update_payment_status(self, stripe_obj, new_status):
        intent_id = stripe_obj.get("id")
        object_type = stripe_obj.get("object")

        logger.info("🔄 _update_payment_status called:")
        logger.info("   - Object type: %s", object_type)
        logger.info("   - Intent ID: %s", intent_id)
        logger.info("   - New status: %s", new_status)

        # If we got a charge, resolve back to the payment_intent id
        if object_type == "charge":
            intent_id = stripe_obj.get("payment_intent")
            logger.info("   - Resolved payment_intent from charge: %s", intent_id)

        # Subscription/Invoice flows send payment_intents that are NOT your Booking payments.
        # Those have an invoice on the PI or on the event object; skip noisy DB lookups/logs.
        # (payment_intent.succeeded from subscription invoices should not create/update Payment rows)
        if stripe_obj.get("invoice"):
            logger.info("PI %s is attached to a Stripe invoice; skipping local Payment update.", intent_id)
            return

        payment = None
        try:
            payment = Payment.objects.get(stripe_payment_intent_id=intent_id)
            old_status = payment.status
            payment.status = new_status
            payment.save(update_fields=["status"])

            logger.info(
                " Payment #%s updated: %s → %s (intent: %s)",
                payment.id, old_status, new_status, intent_id
            )
            logger.info(
                "   - Booking ID: %s",
                getattr(getattr(payment, "booking", None), "id", "N/A"),
            )
            logger.info("   - User: %s", payment.user.email)
            logger.info("   - Amount: %s", payment.amount)

        except Payment.DoesNotExist:
            # Only warn for non-subscription PIs (we already early-returned if it was invoice-backed)
            logger.warning("No local Payment row for intent: %s (non-invoice). Skipping.", intent_id)
            return

        # If we do have a corresponding Payment row, optionally emit Klaviyo
        try:
            user = payment.user
            email = getattr(user, "email", None)

            shop = getattr(payment.booking, "shop", None) if hasattr(payment, "booking") else None
            shop_sub = getattr(shop, "subscription", None) if shop else None

            billing_at_risk = (new_status == "failed")

            if email and shop and shop_sub:
                profile_payload = build_profile_payload_for_shop(
                    shop=shop,
                    shop_sub=shop_sub,
                    stripe_subscription_id=getattr(shop_sub, "stripe_subscription_id", None),
                    price_id=getattr(getattr(shop_sub, "plan", None), "stripe_price_id", None) if hasattr(shop_sub, "plan") else None,
                    cancel_at_period_end=False,
                    is_canceled=False,
                    is_at_risk=billing_at_risk,
                )

                event_props = {
                    "booking_id": getattr(payment.booking, "id", None),
                    "amount": str(payment.amount),
                    "currency": "usd",
                    "status": new_status,
                    "is_deposit": payment.is_deposit,
                    "remaining_amount": str(payment.remaining_amount),
                }

                self.send_klaviyo_event(
                    email=email,
                    event_name=("Payment Succeeded" if new_status == "succeeded" else "Payment Failed"),
                    profile=profile_payload,
                    event_props=event_props,
                )

        except Exception as e:
            logger.error("[klaviyo] payment sync failed: %s", e, exc_info=True)



class VerifyShopOnboardingView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, shop_id):
        shop = get_object_or_404(Shop, id=shop_id)

        # Ensure the user is the owner of the shop
        if request.user != shop.owner:
            return Response(
                {"detail": "You are not the owner of this shop."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Retrieve the linked Stripe account
        if not hasattr(shop, "stripe_account") or not shop.stripe_account.stripe_account_id:
            return Response(
                {"detail": "Shop has no Stripe account."},
                status=status.HTTP_404_NOT_FOUND,
            )

        account = stripe.Account.retrieve(shop.stripe_account.stripe_account_id)

        data = {
            "account_id": account.id,
            "charges_enabled": account.charges_enabled,
            "payouts_enabled": account.payouts_enabled,
            "requirements": account.requirements.currently_due,
            "onboarded": account.charges_enabled and account.payouts_enabled,
        }
        return Response(data, status=status.HTTP_200_OK)

class BookingListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Get bookings based on user role and query params:
        - Owner: must provide shop_id
        - User: must provide user_email
        """
        user = request.user
        bookings_queryset = Booking.objects.select_related('user', 'shop', 'slot')
        paginator = BookingCursorPagination()

        # 🔹 Owner case
        if user.role == 'owner':
            shop_id = request.query_params.get('shop_id')
            if not shop_id:
                return Response({"error": "shop_id is required for owners"}, status=status.HTTP_400_BAD_REQUEST)
            bookings_queryset = bookings_queryset.filter(shop_id=shop_id)
            serializer_class = ownerBookingSerializer

        # 🔹 User case
        else:
            user_email = request.query_params.get('user_email')
            if not user_email:
                return Response({"error": "user_email is required"}, status=status.HTTP_400_BAD_REQUEST)

            try:
                target_user = User.objects.get(email=user_email)
            except User.DoesNotExist:
                return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

            bookings_queryset = bookings_queryset.filter(user=target_user)
            serializer_class = userBookingSerializer

            #  Support comma-separated status values
            status_param = request.query_params.get("status")
            if status_param:
                status_list = [s.strip() for s in status_param.split(",") if s.strip()]
                bookings_queryset = bookings_queryset.filter(status__in=status_list)

            exclude_active = request.query_params.get('exclude_active')
            if exclude_active and exclude_active.lower() == "true":
                bookings_queryset = bookings_queryset.exclude(status="active")

        # ----------------------
        # 📊 Stats (full queryset)
        # ----------------------
        total_count = bookings_queryset.count()
        last_7_days_count = bookings_queryset.filter(created_at__gte=now() - timedelta(days=7)).count()
        cancelled_count = bookings_queryset.filter(status="cancelled").count()
        completed_count = bookings_queryset.filter(status="completed").count()

        stats = {
            "total_bookings": total_count,
            "new_bookings": last_7_days_count,
            "cancelled": cancelled_count,
            "completed": completed_count,
        }

        # 🔹 Pagination for results
        page = paginator.paginate_queryset(bookings_queryset, request)
        serializer = serializer_class(page, many=True, context={"request": request})
        paginated_response = paginator.get_paginated_response(serializer.data)

        #  Inject stats into paginated response
        paginated_response.data["stats"] = stats

        return paginated_response
    
VALID_STRIPE_REASONS = {"duplicate", "fraudulent", "requested_by_customer"}

def _norm_reason(v):
    return (str(v).strip().lower().replace("-", "_")) if v else None

class CancelBookingView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, booking_id):
        try:
            booking = Booking.objects.get(id=booking_id)
        except Booking.DoesNotExist:
            return Response({"error": "Booking not found"}, status=status.HTTP_404_NOT_FOUND)

        # only the booker or the shop owner can cancel
        is_owner = (booking.shop.owner == request.user)
        is_booker = (booking.user == request.user)
        if not (is_owner or is_booker):
            return Response({"error": "Not allowed to cancel this booking"}, status=status.HTTP_403_FORBIDDEN)

        # block impossible states early
        if booking.status in ("no-show", "cancelled", "completed"):
            return Response({"error": f"Cannot cancel a booking in status '{booking.status}'"}, status=status.HTTP_400_BAD_REQUEST)

        # normalize reason coming from client; Stripe-safe fallback
        incoming = request.data.get("reason") or request.POST.get("reason")
        reason = _norm_reason(incoming) or "requested_by_customer"
        if reason not in VALID_STRIPE_REASONS:
            reason = "requested_by_customer"

        # OWNER → force full refund
        success, message = booking.cancel_booking(
            reason=reason,
            force_full_refund=is_owner,
        )

        if success:
            serializer_class = ownerBookingSerializer if is_owner else userBookingSerializer
            serializer = serializer_class(booking, context={"request": request})
            return Response({"message": message, "booking": serializer.data}, status=status.HTTP_200_OK)

        return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)
        
class TransactionLogListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        shop_id = request.query_params.get('shop')
        user_email = request.query_params.get('email')

        # Start with all transactions
        transactions = TransactionLog.objects.all()

        # Filter by shop if provided
        if shop_id:
            transactions = transactions.filter(shop_id=shop_id)

        # Filter by user email if provided
        if user_email:
            try:
                user = User.objects.get(email=user_email)
                transactions = transactions.filter(user=user)
            except User.DoesNotExist:
                return Response(
                    {"status": "error", "message": "User with this email does not exist"},
                    status=status.HTTP_404_NOT_FOUND
                )

        # Paginate the queryset
        paginator = TransactionCursorPagination()
        page = paginator.paginate_queryset(transactions, request)
        serializer = TransactionLogSerializer(page, many=True)

        return paginator.get_paginated_response({
            "status": "success",
            "data": serializer.data
        })

# class ApplyCouponAPIView(APIView):
#     permission_classes = [IsAuthenticated]

#     def post(self, request):
#         serializer = ApplyCouponSerializer(data=request.data, context={"request": request})
#         serializer.is_valid(raise_exception=True)

#         # Record usage
#         serializer.create_usage()

#         # Return coupon info
#         coupon_data = CouponSerializer(serializer.instance).data
#         return Response(coupon_data, status=status.HTTP_200_OK)



##########
#new Class
#########
class RemainingPaymentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, booking_id):
        """
        Charge remaining balance for a deposit booking at service time
        """
        try:
            # 1. Get the booking and original payment
            booking = Booking.objects.get(id=booking_id)
            original_payment = booking.payment

            # 2. Check if this is a deposit payment with remaining amount
            if not original_payment.is_deposit or original_payment.remaining_amount <= 0:
                return Response({
                    "detail": "This booking doesn't require a remaining payment"
                }, status=status.HTTP_400_BAD_REQUEST)

            # 3. Check authorization (customer or shop owner)
            if (booking.user != request.user and
                    booking.shop.owner != request.user):
                return Response({
                    "detail": "Not authorized to process this payment"
                }, status=status.HTTP_403_FORBIDDEN)

            # 4. Get Stripe customer and shop account
            user_customer = original_payment.user.stripe_customer
            shop_account = booking.shop.stripe_account

            if not user_customer.stripe_customer_id:
                return Response({
                    "detail": "Customer not found in Stripe"
                }, status=status.HTTP_400_BAD_REQUEST)

            if not shop_account.stripe_account_id:
                return Response({
                    "detail": "Shop Stripe account not found"
                }, status=status.HTTP_400_BAD_REQUEST)

            # 5. Create PaymentIntent for remaining amount
            remaining_cents = int(original_payment.remaining_amount * 100)

            payment_intent = stripe.PaymentIntent.create(
                amount=remaining_cents,
                currency='usd',
                customer=user_customer.stripe_customer_id,
                payment_method_types=['card'],
                transfer_data={'destination': shop_account.stripe_account_id},
                metadata={
                    'booking_id': booking.id,
                    'original_payment_id': original_payment.id,
                    'payment_type': 'remaining_balance'
                }
            )

            # 6. Create new Payment record for remaining amount
            remaining_payment = Payment.objects.create(
                booking=original_payment.booking,
                user=original_payment.user,
                amount=original_payment.remaining_amount,
                stripe_payment_intent_id=payment_intent.id,
                status='pending',
                is_deposit=False,
                deposit_amount=0.00,
                remaining_amount=0.00
            )

            return Response({
                "payment_id": remaining_payment.id,
                "client_secret": payment_intent.client_secret,
                "payment_intent_id": payment_intent.id,
                "amount": original_payment.remaining_amount,
                "message": "Remaining payment initiated successfully"
            }, status=status.HTTP_200_OK)

        except Booking.DoesNotExist:
            return Response({
                "detail": "Booking not found"
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                "detail": f"Error processing remaining payment: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class MarkBookingNoShowView(APIView):
    """
    Allows a shop owner to mark a booking as a 'no-show'.
    This action will trigger the AI auto-fill process via a Django signal.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, booking_id):
        try:
            # Ensure the booking exists and belongs to the authenticated owner's shop
            booking = Booking.objects.get(id=booking_id, shop__owner=request.user)
        except Booking.DoesNotExist:
            return Response(
                {"error": "Booking not found or you do not have permission to modify it."}, 
                status=status.HTTP_404_NOT_FOUND
            )

        # Check if the booking's current status allows this action
        if booking.status not in ['active', 'completed']:
            return Response(
                {"error": f"This booking cannot be marked as a no-show because its status is '{booking.status}'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Update the status to 'no-show'
        booking.status = 'no-show'
        booking.save(update_fields=['status'])
        
        logger.info(f"Booking {booking_id} was marked as 'no-show' by owner {request.user.email}.")
        
        # The 'on_booking_status_change' signal you already wrote in api/models.py
        # will now automatically trigger the 'trigger_no_show_auto_fill' Celery task.
        
        return Response(
            {"success": True, "message": f"Booking {booking_id} has been marked as a no-show and the AI auto-fill process has been initiated."},
            status=status.HTTP_200_OK
        )