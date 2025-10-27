# payments/views.py

import os
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
from datetime import timedelta
from django.utils.timezone import now
from django.conf import settings
from rest_framework.exceptions import ValidationError
from api.models import Shop, Coupon
from api.serializers import SlotBookingSerializer, CouponSerializer
from accounts.models import User
from api.utils.slots import assert_slot_bookable
from api.utils.zapier import send_klaviyo_event
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
from django.db import transaction
from dateutil.relativedelta import relativedelta
from django.utils import timezone
import datetime


logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY
STRIPE_ENDPOINT_SECRET = settings.STRIPE_ENDPOINT_SECRET


def _update_shop_from_subscription_obj(sub_obj, shop_hint=None):
    """
    Persist the plan + correct period window from Stripe.
    Tolerates 'latest_invoice' being already expanded, and missing/None period timestamps.
    """

    # Make sure we have expanded data we rely on.
    # Also try to expand latest_invoice.lines.period because we use that to infer start/end.
    if not (sub_obj.get("items") or {}).get("data"):
        sub_obj = stripe.Subscription.retrieve(
            sub_obj["id"],
            expand=["items.data.price", "latest_invoice.lines.data.period"],
        )

    items = (sub_obj.get("items") or {}).get("data") or []
    if not items:
        logger.error("Subscription %s has no items; cannot map plan", sub_obj.get("id"))
        return

    price_id = (items[0].get("price") or {}).get("id")
    ai_price_id = getattr(settings, "STRIPE_AI_PRICE_ID", None)

    # ─────────────────────────────────────────
    # 1. AI add-on branch (unchanged logic, but safer logging)
    # ─────────────────────────────────────────
    if price_id == ai_price_id:
        meta = sub_obj.get("metadata") or {}
        shop_id = meta.get("shop_id")
        if shop_id:
            try:
                shop = Shop.objects.get(id=int(shop_id))
            except Shop.DoesNotExist:
                logger.warning("⚠️ Shop not found for AI add-on metadata: %s", shop_id)
                return

            if hasattr(shop, "subscription"):
                ss = shop.subscription
                ss.has_ai_addon = True
                ss.ai_subscription_id = sub_obj.get("id")

                # find AI item id
                ai_item = next(
                    (
                        it
                        for it in items
                        if (it.get("price") or {}).get("id") == ai_price_id
                    ),
                    None,
                )
                ss.ai_subscription_item_id = (ai_item or {}).get("id")

                ss.save(
                    update_fields=[
                        "has_ai_addon",
                        "ai_subscription_id",
                        "ai_subscription_item_id",
                    ]
                )
                logger.info(
                    " AI add-on activated for shop %s (sub %s)",
                    shop_id,
                    sub_obj.get("id"),
                )
        return  # stop here — AI add-on does not map to base plan

    # ─────────────────────────────────────────
    # 2. Resolve the base plan
    # ─────────────────────────────────────────
    try:
        plan = SubscriptionPlan.objects.get(stripe_price_id=price_id)
    except SubscriptionPlan.DoesNotExist:
        logger.error("No SubscriptionPlan with stripe_price_id=%s", price_id)
        return

    # ─────────────────────────────────────────
    # 3. Resolve which shop this subscription belongs to
    # ─────────────────────────────────────────
    shop = shop_hint

    if not shop:
        meta = sub_obj.get("metadata") or {}
        sid = meta.get("shop_id")
        if sid:
            try:
                shop = Shop.objects.get(id=int(sid))
            except Exception:
                shop = None

    if not shop:
        ss = (
            ShopSubscription.objects
            .filter(stripe_subscription_id=sub_obj["id"])
            .select_related("shop")
            .first()
        )
        if ss:
            shop = ss.shop

    if not shop:
        cust_id = sub_obj.get("customer")
        if cust_id:
            usc = (
                UserStripeCustomer.objects
                .filter(stripe_customer_id=cust_id)
                .select_related("user")
                .first()
            )
            if usc:
                shop = Shop.objects.filter(owner=usc.user).order_by("id").first()

    if not shop:
        logger.error(
            "Could not resolve shop for subscription %s",
            sub_obj.get("id"),
        )
        return

    # ─────────────────────────────────────────
    # 4. Resolve billing period start / end safely
    # ─────────────────────────────────────────
    ps_ts = sub_obj.get("current_period_start")
    pe_ts = sub_obj.get("current_period_end")

    needs_invoice_fallback = (
        not ps_ts or not pe_ts or ps_ts == pe_ts
    )

    if needs_invoice_fallback and sub_obj.get("latest_invoice"):
        invoice_obj = None
        invoice_id = None
        latest_invoice = sub_obj.get("latest_invoice")

        # Case A: Stripe already expanded latest_invoice into a dict
        if isinstance(latest_invoice, dict):
            invoice_obj = latest_invoice
            invoice_id = latest_invoice.get("id")

        # Case B: latest_invoice is just an ID string, we have to retrieve/expand
        elif isinstance(latest_invoice, str):
            invoice_id = latest_invoice
            try:
                invoice_obj = stripe.Invoice.retrieve(
                    invoice_id,
                    expand=["lines.data.period"],
                )
            except Exception as e:
                logger.exception(
                    "Could not retrieve invoice %s for sub %s: %s",
                    invoice_id,
                    sub_obj.get("id"),
                    e,
                )
                invoice_obj = None

        # Extract period info from invoice lines if we got anything
        if invoice_obj:
            try:
                line_items = (
                    (invoice_obj.get("lines") or {}).get("data") or []
                )
            except AttributeError:
                line_items = []

            if line_items:
                period_block = line_items[0].get("period") or {}
                # only fill them if still missing / bogus
                ps_ts = ps_ts or period_block.get("start")
                pe_ts = pe_ts or period_block.get("end")

    # Last resort: if Stripe STILL didn't give us dates, synthesize 1-month window.
    # This prevents a crash in datetime.fromtimestamp(None)
    if not ps_ts or not pe_ts:
        now_utc = timezone.now()
        # store as epoch seconds
        ps_ts = ps_ts or int(now_utc.timestamp())
        pe_ts = pe_ts or int(
            (now_utc + relativedelta(months=1)).timestamp()
        )

    # ─────────────────────────────────────────
    # 5. Convert timestamps to aware datetimes
    # ─────────────────────────────────────────
    import datetime as _dt_mod

    start_dt = _dt_mod.datetime.fromtimestamp(
        ps_ts, tz=_dt_mod.timezone.utc
    )
    end_dt = _dt_mod.datetime.fromtimestamp(
        pe_ts, tz=_dt_mod.timezone.utc
    )

    # Safety: if identical, bump end by one month
    if start_dt == end_dt:
        logger.warning(
            "Dates identical for sub %s. Forcing +1 month.",
            sub_obj.get("id"),
        )
        end_dt = start_dt + relativedelta(months=1)

    # ─────────────────────────────────────────
    # 6. Upsert ShopSubscription
    # ─────────────────────────────────────────
    obj, created = ShopSubscription.objects.get_or_create(
        shop=shop,
        defaults={"plan": plan, "status": ShopSubscription.STATUS_ACTIVE},
    )

    obj.plan = plan
    obj.status = ShopSubscription.STATUS_ACTIVE
    obj.stripe_subscription_id = sub_obj.get("id")
    obj.start_date = start_dt
    obj.end_date = end_dt
    obj.save(
        update_fields=[
            "plan",
            "status",
            "stripe_subscription_id",
            "start_date",
            "end_date",
        ]
    )

    try:
        owner = shop.owner  # shop.owner is the account paying
        email = getattr(owner, "email", None)

        if email:
            profile_payload = {
                "plan": plan.name if plan else None,
                "plan_status": obj.status,  # active / trialing / etc.
                "ai_addon": bool(getattr(obj, "has_ai_addon", False)),
                "legacy_500": bool(getattr(obj, "legacy_ai_promo_used", False)),
                "next_billing_date": obj.end_date.isoformat() if obj.end_date else None,
                "trial_end": obj.end_date.isoformat() if obj.status == "trialing" else None,
                "stripe_customer_id": (
                    getattr(
                        getattr(owner, "stripe_customer", None),
                        "stripe_customer_id",
                        None,
                    )
                ),
                "stripe_subscription_id": sub_obj.get("id"),
                "price_id": price_id,
                "shop_id": shop.id,
            }

            # figure out event name
            if created:
                ev_name = "Subscription Purchased"
            else:
                ev_name = "Subscription Updated"

            event_props = {
                "shop_id": shop.id,
                "plan_name": plan.name if plan else None,
                "status": obj.status,
                "period_start": obj.start_date.isoformat() if obj.start_date else None,
                "period_end": obj.end_date.isoformat() if obj.end_date else None,
                "application_fee_percent": getattr(plan, "commission_rate", None),
            }

            send_klaviyo_event(
                email=email,
                event_name=ev_name,
                profile=profile_payload,
                event_props=event_props,
            )

    except Exception as e:
        logger.error("[klaviyo] sub sync failed for shop %s: %s", shop.id, e, exc_info=True)

    logger.info(
        " Shop %s set to plan %s via subscription %s (%s → %s)",
        shop.id,
        plan.name,
        sub_obj.get("id"),
        obj.start_date.isoformat(),
        obj.end_date.isoformat(),
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
        # HARD GUARD: slot must be in the future and have capacity
        slot = Slot.objects.select_for_update().filter(id=slot_id).first()
        if not slot:
            return Response({"detail": "Slot not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            # Optional tiny grace if you want: grace_minutes=2
            assert_slot_bookable(slot)  
        except ValidationError as e:
            return Response({"detail": str(e.detail[0] if isinstance(e.detail, list) else e.detail)},
                            status=status.HTTP_400_BAD_REQUEST)
        # 2) Create booking via SlotBookingSerializer
        # proceed to create the SlotBooking
        serializer = SlotBookingSerializer(
            data={"slot_id": slot_id},
            context={"request": request},
        )
        try:
            serializer.is_valid(raise_exception=True)
            booking = serializer.save()
        except ValidationError as e:
            return Response(
                {"detail": extract_validation_error_message(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
                # Fall back to Foundation, then any plan; else no commission
                try:
                    plan = (
                        SubscriptionPlan.objects.filter(
                            name=SubscriptionPlan.FOUNDATION
                        ).first()
                        or SubscriptionPlan.objects.order_by("id").first()
                    )
                except Exception:
                    plan = None

                # Soft-seed a ShopSubscription for legacy shops (optional)
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

            # 6) Price minus coupon
            total_amount = (
                booking.service.discount_price
                if booking.service.discount_price > 0
                else booking.service.price
            )
            total_amount = float(total_amount)

            # 5. Calculate final price after coupon
            total_amount = booking.service.discount_price if booking.service.discount_price > 0 else booking.service.price
            full_service_amount = total_amount  # Save original amount before deposit calculation

            if shop.is_deposit_required:
                service = booking.service
                # Use the pre-calculated deposit amount from service
                deposit_amount = service.deposit_amount if service.deposit_amount else full_service_amount
                total_amount = min(deposit_amount, full_service_amount)
            else:
                deposit_amount = full_service_amount

            remaining_balance = full_service_amount - total_amount if shop.is_deposit_required else Decimal('0.00')
            total_amount = float(total_amount)

            if coupon:
                if coupon.in_percentage:
                    discount = (total_amount * float(coupon.amount)) / 100.0
                else:
                    discount = float(coupon.amount)
                total_amount = max(total_amount - discount, 0.0)
                # record usage only after successful validation
                coupon_serializer.create_usage()

            # 7) Compute application fee (commission)
            application_fee_cents = 0
            try:
                commission_rate = float(plan.commission_rate) if plan and plan.commission_rate is not None else 0.0
            except Exception:
                commission_rate = 0.0

            if commission_rate > 0:
                commission = (total_amount * commission_rate) / 100.0
                application_fee_cents = int(round(commission * 100))

            # 8) Create PaymentIntent (Connect destination charges)
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

            print(f"PaymentIntent created: {intent.id}")
            print(f"About to create payment for booking {booking.id}")

            # 9) Persist Payment row
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
                        "deposit_amount": deposit_amount if shop.is_deposit_required else 0,  # Fix: use calculated deposit_amount
                        "remaining_amount": remaining_balance,
                        "deposit_paid": 0,   # 👈 add this
                        "tips_amount": 0,
                        "application_fee_amount": 0,
                        "payment_type": "full",

                    },
                )
                # print(f" Payment saved: ID={payment.id}, Created={created}")

            # 10) Ephemeral key for mobile SDKs
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
            # If needed, your Celery auto-cancel can clean up failed payments/holds later.
            import traceback
            print(f"ERROR in payment creation: {str(e)}")
            print(f"Traceback: {traceback.format_exc()}")
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
        if event_type == "payment_intent.succeeded":
            self._update_payment_status(data, "succeeded")
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
        if event_type == "checkout.session.completed":
            session = data
            shop_ref = session.get("client_reference_id")
            sub_id = session.get("subscription")

            shop_hint = None
            if shop_ref:
                try:
                    shop_hint = Shop.objects.get(id=int(shop_ref))
                    logger.info("[checkout] resolved shop_hint=%s", shop_hint.id)
                except Exception:
                    logger.warning("[checkout] bad client_reference_id: %r", shop_ref)

            if sub_id:
                sub = stripe.Subscription.retrieve(
                    sub_id,
                    expand=["items.data.price", "latest_invoice.payment_intent"]
                )
                sub_meta = sub.get("metadata") or {}

                # ensure subscription.metadata.shop_id is set in Stripe for future webhooks
                if shop_hint:
                    try:
                        if str(sub_meta.get("shop_id")) != str(shop_hint.id):
                            stripe.Subscription.modify(
                                sub["id"],
                                metadata={**sub_meta, "shop_id": str(shop_hint.id)}
                            )
                    except Exception:
                        logger.exception(
                            "Failed to set subscription metadata.shop_id"
                        )

                price_ids = [
                    it["price"]["id"]
                    for it in (sub.get("items", {}).get("data") or [])
                ]
                ai_price_id = getattr(settings, "STRIPE_AI_PRICE_ID", None)
                is_ai_addon = (
                    sub_meta.get("addon") == "ai_assistant"
                    or (ai_price_id and ai_price_id in price_ids)
                )

                if is_ai_addon:
                    # Mark AI add-on active and legacy promo if applicable
                    if shop_hint and hasattr(shop_hint, "subscription"):
                        ss = shop_hint.subscription
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

                        # Check invoice discounts for legacy promo
                        try:
                            inv = sub.get("latest_invoice")
                            if isinstance(inv, str):
                                inv = stripe.Invoice.retrieve(
                                    inv,
                                    expand=[
                                        "discounts",
                                        "discounts.discount.coupon",
                                    ],
                                )
                            discounts = inv.get("discounts", []) if inv else []
                            if any(
                                d.get("discount", {})
                                .get("coupon", {})
                                .get("id")
                                == settings.STRIPE_LEGACY_COUPON_ID
                                for d in discounts
                            ):
                                ss.legacy_ai_promo_used = True
                                logger.info(
                                    "✅ LEGACY promo applied for shop %s",
                                    shop_hint.id,
                                )
                        except Exception:
                            logger.exception("Promo detection failed")

                        ss.save(
                            update_fields=[
                                "has_ai_addon",
                                "ai_subscription_id",
                                "ai_subscription_item_id",
                                "legacy_ai_promo_used",
                            ]
                        )
                        logger.info(
                            "✅ AI Assistant add-on enabled for shop %s",
                            shop_hint.id,
                        )
                    return Response(status=200)

                # base plan purchase / upgrade
                _update_shop_from_subscription_obj(sub, shop_hint=shop_hint)

            return Response(status=200)

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
            stripe_sub = data  # <-- local var for this event

            try:
                # 1. Downgrade their plan in our DB
                shop_sub = ShopSubscription.objects.get(
                    stripe_subscription_id=stripe_sub["id"]
                )
            except ShopSubscription.DoesNotExist:
                # nothing to downgrade, but we still want to attempt Klaviyo
                shop_sub = None

            if shop_sub:
                try:
                    foundation = SubscriptionPlan.objects.get(
                        name=SubscriptionPlan.FOUNDATION
                    )
                except SubscriptionPlan.DoesNotExist:
                    foundation = None  # fallback if somehow missing

                # Keep them "active" on Foundation basically forever
                shop_sub.plan = foundation
                shop_sub.status = ShopSubscription.STATUS_ACTIVE
                shop_sub.stripe_subscription_id = None
                shop_sub.end_date = timezone.now() + relativedelta(years=100)
                shop_sub.save()

                # 2. Sync to Klaviyo (cancellation event + profile update)
                owner = shop_sub.shop.owner
                email = getattr(owner, "email", None)

                if email:
                    profile_payload = {
                        "plan": (
                            shop_sub.plan.name if shop_sub.plan else None
                        ),
                        "plan_status": "canceled",
                        "ai_addon": bool(
                            getattr(shop_sub, "has_ai_addon", False)
                        ),
                        "legacy_500": bool(
                            getattr(shop_sub, "legacy_ai_promo_used", False)
                        ),
                        "next_billing_date": None,
                        "trial_end": None,
                        "stripe_customer_id": getattr(
                            getattr(owner, "stripe_customer", None),
                            "stripe_customer_id",
                            None,
                        ),
                        "stripe_subscription_id": stripe_sub.get("id"),
                        "price_id": None,
                        "shop_id": shop_sub.shop.id,
                    }

                    event_props = {
                        "shop_id": shop_sub.shop.id,
                        "reason": "user_cancelled",
                    }

                    try:
                        send_klaviyo_event(
                            email=email,
                            event_name="Subscription Canceled",
                            profile=profile_payload,
                            event_props=event_props,
                        )
                    except Exception as e:
                        logger.error(
                            "[klaviyo] cancel sync failed: %s",
                            e,
                            exc_info=True,
                        )

            return Response(status=200)

        # ------------------------------------------------------------------
        # Fallback
        # ------------------------------------------------------------------
        logger.warning("⚠️ Unhandled event: %s", event_type)
        return Response(status=200)

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

        if object_type == "charge":
            # charges don't directly have our Payment row,
            # so map back to the payment_intent
            intent_id = stripe_obj.get("payment_intent")
            logger.info(
                "   - Resolved payment_intent from charge: %s", intent_id
            )

        try:
            payment = Payment.objects.get(
                stripe_payment_intent_id=intent_id
            )
            old_status = payment.status
            payment.status = new_status
            payment.save(update_fields=["status"])

            logger.info(
                " Payment #%s updated: %s → %s (intent: %s)",
                payment.id,
                old_status,
                new_status,
                intent_id,
            )
            logger.info(
                "   - Booking ID: %s",
                payment.booking.id if hasattr(payment, "booking") else "N/A",
            )
            logger.info("   - User: %s", payment.user.email)
            logger.info("   - Amount: %s", payment.amount)

        except Payment.DoesNotExist:
            logger.error(
                "❌ Payment NOT FOUND for intent: %s", intent_id
            )
            logger.error("   - Checking all payments in DB...")
            all_intents = list(
                Payment.objects.values_list(
                    "stripe_payment_intent_id", flat=True
                )[:10]
            )
            logger.error(
                "   - Existing payment intents: %s", all_intents
            )

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