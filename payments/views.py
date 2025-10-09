import os
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import stripe
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

from dateutil.relativedelta import relativedelta
from django.utils import timezone
import datetime


logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY
STRIPE_ENDPOINT_SECRET = settings.STRIPE_ENDPOINT_SECRET


def _update_shop_from_subscription_obj(sub_obj, shop_hint=None):
    """
    sub_obj: stripe.Subscription dict (may be partial)
    shop_hint: a Shop instance if you already resolved it (optional)
    """
    # Ensure we have items->price populated
    if not (sub_obj.get("items") or {}).get("data"):
        sub_obj = stripe.Subscription.retrieve(sub_obj["id"], expand=["items.data.price"])

    # Map price -> local plan
    items = (sub_obj.get("items") or {}).get("data") or []
    if not items:
        logger.error("Subscription %s has no items; cannot map plan", sub_obj.get("id"))
        return
    price_id = (items[0].get("price") or {}).get("id")
    if not price_id:
        logger.error("Subscription %s missing price.id", sub_obj.get("id"))
        return

    try:
        plan = SubscriptionPlan.objects.get(stripe_price_id=price_id)
    except SubscriptionPlan.DoesNotExist:
        logger.error("No SubscriptionPlan with stripe_price_id=%s", price_id)
        return

    # Resolve shop if not passed
    # Resolve shop if not passed
    shop = shop_hint

    # A) First, use subscription metadata (set during checkout)
    if not shop:
        meta = sub_obj.get("metadata") or {}
        shop_id_meta = meta.get("shop_id")
        if shop_id_meta:
            try:
                shop = Shop.objects.get(id=int(shop_id_meta))
            except Exception:
                shop = None

    # B) Then, any existing ShopSubscription record that already linked this subscription
    if not shop:
        ss = ShopSubscription.objects.filter(stripe_subscription_id=sub_obj["id"]).select_related("shop").first()
        if ss:
            shop = ss.shop

    # C) Finally, map Stripe customer -> owner -> shop
    if not shop:
        cust_id = sub_obj.get("customer")
        if cust_id:
            usc = UserStripeCustomer.objects.filter(stripe_customer_id=cust_id).select_related("user").first()
            if usc:
                # If an owner can have multiple shops, refine this selection if needed.
                shop = Shop.objects.filter(owner=usc.user).order_by("id").first()

    if not shop:
        logger.error("Could not resolve shop for subscription %s", sub_obj.get("id"))
        return


    # Compute period end
    period_end_ts = sub_obj.get("current_period_end")
    if not period_end_ts:
        latest_inv_id = sub_obj.get("latest_invoice")
        if latest_inv_id:
            inv = stripe.Invoice.retrieve(latest_inv_id)
            period_end_ts = inv.get("period_end")
    end_dt = timezone.now() + relativedelta(months=1)
    if period_end_ts:
        import datetime
        end_dt = datetime.datetime.fromtimestamp(period_end_ts, tz=datetime.timezone.utc)

    ShopSubscription.objects.update_or_create(
        shop=shop,
        defaults={
            "plan": plan,
            "status": ShopSubscription.STATUS_ACTIVE,
            "stripe_subscription_id": sub_obj.get("id"),
            "start_date": timezone.now(),
            "end_date": end_dt,
        },
    )
    logger.info("✅ Shop %s set to plan %s via subscription %s (ends %s)",
                shop.id, plan.name, sub_obj.get("id"), end_dt.isoformat())

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

        # 2) Create booking via SlotBookingSerializer
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

            # 9) Persist Payment row
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
                "deposit_amount": 0,   # <- important
                "remaining_amount": remaining_balance,
                "deposit_paid": 0,   # 👈 add this
                "tips_amount": 0,
                "application_fee_amount": 0,
                "payment_type": "full",

            },
            )

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

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_ENDPOINT_SECRET)
        except ValueError:
            return Response({"error": "Invalid payload"}, status=400)
        except stripe.error.SignatureVerificationError:
            return Response({"error": "Invalid signature"}, status=400)

        event_type = event["type"]
        data = event["data"]["object"]

        logger.info("Stripe event: %s (livemode=%s)", event_type, bool(event.get("livemode")))

        # --- payments (keep your existing handlers) ---
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

        # --- Connect transfers (optional) ---
        if event_type.startswith("transfer."):
            logger.info("Transfer event: %s %s", event_type, data.get("id"))
            return Response(status=200)

        # --- Checkout completion → create/attach subscription ---
        if event_type == "checkout.session.completed":
            try:
                session = data
                shop_ref = session.get("client_reference_id")
                sub_id   = session.get("subscription")

                logger.info("[checkout] completed session=%s shop_ref=%s sub_id=%s",
                            session.get("id"), shop_ref, sub_id)

                shop_hint = None
                if shop_ref:
                    try:
                        shop_hint = Shop.objects.get(id=int(shop_ref))
                        logger.info("[checkout] resolved shop_hint=%s from client_reference_id", shop_hint.id)
                    except Exception:
                        logger.warning("[checkout] bad client_reference_id: %r", shop_ref)

                if sub_id:
                    # Normal path: fetch subscription, map by subscription price
                    sub = stripe.Subscription.retrieve(sub_id, expand=["items.data.price"])
                    _update_shop_from_subscription_obj(sub, shop_hint=shop_hint)
                    try:
                        current_meta = sub.get("metadata") or {}
                        if shop_hint and str(current_meta.get("shop_id")) != str(shop_hint.id):
                            stripe.Subscription.modify(sub["id"], metadata={**current_meta, "shop_id": str(shop_hint.id)})
                    except Exception:
                        logger.exception("Failed to set subscription metadata.shop_id")

                    return Response(status=200)

                # Fallback (rare): no subscription on session → try line_items
                # This also helps you debug wrong price ids.
                try:
                    session_full = stripe.checkout.Session.retrieve(session["id"], expand=["line_items.data.price"])
                    li = (session_full.get("line_items") or {}).get("data") or []
                    price_id = li and (li[0].get("price") or {}).get("id")
                    logger.info("[checkout] fallback price_id from line_items: %s", price_id)
                    if price_id and shop_hint:
                        try:
                            plan = SubscriptionPlan.objects.get(stripe_price_id=price_id)
                            ShopSubscription.objects.update_or_create(
                                shop=shop_hint,
                                defaults={
                                    "plan": plan,
                                    "status": ShopSubscription.STATUS_ACTIVE,
                                    "stripe_subscription_id": None,  # unknown here
                                    "start_date": timezone.now(),
                                    "end_date": timezone.now() + relativedelta(months=1),
                                },
                            )
                            logger.info("✅ Shop %s set to plan %s via CHECKOUT fallback", shop_hint.id, plan.name)
                        except SubscriptionPlan.DoesNotExist:
                            known = list(SubscriptionPlan.objects.values_list("name", "stripe_price_id"))
                            logger.error("[checkout] fallback: no local plan for price_id=%s. Known: %s", price_id, known)
                except Exception:
                    logger.exception("[checkout] fallback retrieval failed")

                return Response(status=200)
            except Exception:
                logger.exception("checkout.session.completed error")
                return Response(status=500)


        # --- subscription lifecycle ---
        if event_type in ("customer.subscription.created", "customer.subscription.updated"):
            _update_shop_from_subscription_obj(data)
            return Response(status=200)

        # --- invoice paid (support old/new names) ---
        if event_type in ("invoice.payment_succeeded", "invoice.paid", "invoice_payment.paid"):
            sub_id = data.get("subscription")
            if sub_id:
                try:
                    sub = stripe.Subscription.retrieve(sub_id, expand=["items.data.price"])
                    _update_shop_from_subscription_obj(sub)
                except Exception as e:
                    logger.exception("invoice handler failed for %s: %s", sub_id, e)
            return Response(status=200)

        # --- subscription cancelled ---
        if event_type == "customer.subscription.deleted":
            stripe_sub = data
            try:
                shop_sub = ShopSubscription.objects.get(stripe_subscription_id=stripe_sub['id'])
                foundation = SubscriptionPlan.objects.get(name=SubscriptionPlan.FOUNDATION)
                shop_sub.plan = foundation
                shop_sub.status = ShopSubscription.STATUS_ACTIVE
                shop_sub.stripe_subscription_id = None
                shop_sub.end_date = timezone.now() + relativedelta(years=100)
                shop_sub.save()
            except ShopSubscription.DoesNotExist:
                pass
            return Response(status=200)

        logger.warning("⚠️ Unhandled event: %s", event_type)
        return Response(status=200)

    def _update_payment_status(self, stripe_obj, new_status):
        intent_id = stripe_obj.get("id")
        if stripe_obj.get("object") == "charge":
            intent_id = stripe_obj.get("payment_intent")

        try:
            payment = Payment.objects.get(stripe_payment_intent_id=intent_id)
            payment.status = new_status
            payment.save(update_fields=["status"])
            logger.info("✅ Payment %s → %s", intent_id, new_status)
        except Payment.DoesNotExist:
            logger.warning("⚠️ Payment with intent %s not found", intent_id)

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

            # ✅ Support comma-separated status values
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

        # ✅ Inject stats into paginated response
        paginated_response.data["stats"] = stats

        return paginated_response
    
class CancelBookingView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, booking_id):
        try:
            booking = Booking.objects.get(id=booking_id)
        except Booking.DoesNotExist:
            return Response({"error": "Booking not found"}, status=status.HTTP_404_NOT_FOUND)

        # ✅ Check if request user is either the booker OR the shop owner
        if booking.user != request.user and booking.shop.owner != request.user:
            return Response({"error": "Not allowed to cancel this booking"}, status=status.HTTP_403_FORBIDDEN)

        success, message = booking.cancel_booking(reason="cancelled_by_owner" if booking.shop.owner == request.user else "requested_by_customer")

        if success:
            # Use correct serializer depending on who cancelled
            serializer_class = ownerBookingSerializer if booking.shop.owner == request.user else userBookingSerializer
            serializer = serializer_class(booking, context={"request": request})
            return Response({"message": message, "booking": serializer.data}, status=status.HTTP_200_OK)
        else:
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
