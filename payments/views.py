import os
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import stripe
import json
from datetime import timedelta
from django.utils.timezone import now
from django.conf import settings

from api.models import Shop, Coupon
from api.serializers import SlotBookingSerializer, CouponSerializer
from accounts.models import User
from .models import Payment, UserStripeCustomer, Booking, TransactionLog, CouponUsage, can_use_coupon
from .serializers import userBookingSerializer, ownerBookingSerializer, TransactionLogSerializer, ApplyCouponSerializer
from .pagination import BookingCursorPagination, TransactionCursorPagination
from api.tasks import auto_cancel_booking
import logging
logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY
STRIPE_ENDPOINT_SECRET = settings.STRIPE_ENDPOINT_SECRET

class CreatePaymentIntentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, slot_id):
        user = request.user
        coupon_id = request.data.get("coupon_id", None)

        # 1. Create Booking
        serializer = SlotBookingSerializer(
            data={"slot_id": slot_id},
            context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        booking = serializer.save()

        try:
            # 2. Ensure Stripe Customer exists
            user_customer, _ = UserStripeCustomer.objects.get_or_create(user=user)
            if not user_customer.stripe_customer_id:
                stripe_customer = stripe.Customer.create(email=user.email)
                user_customer.stripe_customer_id = stripe_customer.id
                user_customer.save()

            # 3. Ensure Shop Stripe Account exists
            shop = booking.shop
            shop_account = getattr(shop, "stripe_account", None)
            if not shop_account:
                self._cancel_booking(booking.id)
                return Response({"error": "Shop Stripe account not found"}, status=400)

            # 4. Calculate price
            total_amount = (
                booking.service.discount_price
                if booking.service.discount_price > 0
                else booking.service.price
            )

            coupon = None
            discount = 0

            # 5. Apply Coupon
            if coupon_id:
                coupon_serializer = ApplyCouponSerializer(
                    data={"coupon_id": coupon_id},
                    context={"request": request}
                )
                if coupon_serializer.is_valid():
                    coupon = coupon_serializer.instance
                    if coupon.in_percentage:
                        discount = (total_amount * coupon.amount) / 100
                    else:
                        discount = coupon.amount
                    total_amount = max(total_amount - discount, 0)
                    coupon_serializer.create_usage()
                else:
                    self._cancel_booking(booking.id)
                    return Response({"error": coupon_serializer.errors}, status=400)

            # 6. Create PaymentIntent
            amount_cents = int(total_amount * 100)
            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency="usd",
                customer=user_customer.stripe_customer_id,
                payment_method_types=["card"],
                transfer_data={"destination": shop_account.stripe_account_id},
                metadata={"booking_id": booking.id}
            )

            # 7. Save Payment
            Payment.objects.update_or_create(
                booking=booking,
                defaults={
                    "user": user,
                    "amount": total_amount,
                    "coupon": coupon,
                    "coupon_amount": discount if coupon else None,
                    "stripe_payment_intent_id": intent.id,
                    "status": "pending",
                },
            )

            # 8. Create Ephemeral Key
            ephemeral_key = stripe.EphemeralKey.create(
                customer=user_customer.stripe_customer_id,
                stripe_version="2024-04-10"
            )

            return Response({
                "booking_id": booking.id,
                "client_secret": intent.client_secret,
                "payment_intent_id": intent.id,
                "ephemeral_key": ephemeral_key.secret,
                "customer_id": user_customer.stripe_customer_id,
                "coupon_applied": bool(coupon)
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.exception("Error in CreatePaymentIntentView: %s", str(e))
            self._cancel_booking(booking.id)
            return Response({"error": str(e)}, status=500)

    def _cancel_booking(self, booking_id):
        try:
            auto_cancel_booking.apply_async((booking_id,), countdown=5 * 60)  # 5 mins
        except Exception as exc:
            logger.exception("Failed to enqueue auto_cancel_booking for booking_id=%s: %s", booking_id, exc)

class ShopOnboardingLinkView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, shop_id):
        
        shop = get_object_or_404(Shop, id=shop_id)
        user = request.user
        if getattr(user, "role", None) != "owner":
            return Response({"detail": "Only owner can view services."}, status=status.HTTP_403_FORBIDDEN)

        base_url = os.getenv("BASE_URL", "https://yourdomain.com")

        account_link = stripe.AccountLink.create(
            account=shop.stripe_account.stripe_account_id,
            refresh_url=f"{base_url}/stripe/refresh",
            return_url=f"{base_url}/stripe/return",
            type="account_onboarding"
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
    authentication_classes = []  # Disable authentication for webhook
    permission_classes = []      # Disable permission checks

    def post(self, request, *args, **kwargs):
        payload = request.body
        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, STRIPE_ENDPOINT_SECRET
            )
        except ValueError:
            # Invalid payload
            return Response({"error": "Invalid payload"}, status=400)
        except stripe.error.SignatureVerificationError:
            # Invalid signature
            return Response({"error": "Invalid signature"}, status=400)

        event_type = event["type"]
        data = event["data"]["object"]

        # --- Handle PaymentIntents (recommended way to track payments) ---
        if event_type == "payment_intent.succeeded":
            self._update_payment_status(data, "succeeded")

        elif event_type == "payment_intent.payment_failed":
            self._update_payment_status(data, "failed")

        elif event_type == "payment_intent.canceled":
            self._update_payment_status(data, "cancelled")

        # --- Handle Charges (optional, useful for extra logging) ---
        elif event_type == "charge.succeeded":
            self._update_payment_status(data, "succeeded")

        elif event_type == "charge.failed":
            self._update_payment_status(data, "failed")

        # --- Handle Transfers / Payouts (if using Connect) ---
        elif event_type.startswith("transfer."):
            # TODO: Update your transfer table if you have one
            print("🔄 Transfer event:", event_type, data["id"])

        else:
            # Log unhandled events for debugging
            print("⚠️ Unhandled event:", event_type)

        return Response(status=200)

    def _update_payment_status(self, stripe_obj, new_status):
        """Helper to safely update your Payment model"""
        intent_id = stripe_obj.get("id")
        if stripe_obj.get("object") == "charge":
            intent_id = stripe_obj.get("payment_intent")  # link charge → intent

        try:
            payment = Payment.objects.get(stripe_payment_intent_id=intent_id)
            payment.status = new_status
            payment.save(update_fields=["status"])
            print(f"✅ Payment {intent_id} updated to {new_status}")
        except Payment.DoesNotExist:
            print(f"⚠️ Payment with intent {intent_id} not found")

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

