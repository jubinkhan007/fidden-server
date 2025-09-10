from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import stripe
import json
from django.conf import settings

from api.models import Shop, SlotBooking
from accounts.models import User
from .models import Payment, UserStripeCustomer, ShopStripeAccount

stripe.api_key = settings.STRIPE_SECRET_KEY
STRIPE_ENDPOINT_SECRET = settings.STRIPE_ENDPOINT_SECRET

# -----------------------------
# 1️⃣ Create PaymentIntent
# -----------------------------
class CreatePaymentIntentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, booking_id):
        booking = get_object_or_404(SlotBooking, id=booking_id)

        # 1. Ensure User Stripe Customer exists
        user = request.user
        user_customer, _ = UserStripeCustomer.objects.get_or_create(user=user)
        if not user_customer.stripe_customer_id:
            stripe_customer = stripe.Customer.create(email=user.email)
            user_customer.stripe_customer_id = stripe_customer.id
            user_customer.save()

        # 2. Ensure Shop Stripe Account exists
        shop = booking.shop
        shop_account = getattr(shop, 'stripe_account', None)
        if not shop_account:
            return Response({"error": "Shop Stripe account not found"}, status=400)

        # 3. Create PaymentIntent
        amount_cents = int(booking.service.price * 100)
        try:
            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency="usd",
                customer=user_customer.stripe_customer_id,
                payment_method_types=["card"],
                transfer_data={"destination": shop_account.stripe_account_id},
                metadata={"booking_id": booking.id}
            )
        except Exception as e:
            return Response({"error": f"PaymentIntent creation failed: {str(e)}"}, status=500)

        # 4. Save Payment record
        Payment.objects.update_or_create(
            booking=booking,
            defaults={
                "user": user,
                "amount": booking.service.price,
                "stripe_payment_intent_id": intent.id,
                "status": "pending"
            }
        )

        return Response({"client_secret": intent.client_secret, "payment_intent_id": intent.id}, status=200)

# -----------------------------
# 2️⃣ Shop Onboarding Link
# -----------------------------
class ShopOnboardingLinkView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, shop_id):
        shop = get_object_or_404(Shop, id=shop_id)
        user = request.user
        if getattr(user, "role", None) != "owner":
            return Response({"detail": "Only owner can view services."}, status=status.HTTP_403_FORBIDDEN)

        account_link = stripe.AccountLink.create(
            account=shop.stripe_account.stripe_account_id,
            refresh_url="https://yourdomain.com/stripe/refresh",
            return_url="https://yourdomain.com/stripe/return",
            type="account_onboarding"
        )
        return Response({"url": account_link.url})

# -----------------------------
# 3️⃣ Save Card View
# -----------------------------
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

# -----------------------------
# 4️⃣ Stripe Webhook
# -----------------------------
@method_decorator(csrf_exempt, name='dispatch')
class StripeWebhookView(APIView):
    authentication_classes = []  # Disable authentication for webhook
    permission_classes = []      # Disable permission checks

    def post(self, request, *args, **kwargs):
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_ENDPOINT_SECRET)
        except ValueError:
            return Response(status=400)
        except stripe.error.SignatureVerificationError:
            return Response(status=400)

        # Handle events
        if event['type'] == 'payment_intent.succeeded':
            intent = event['data']['object']
            booking_id = intent.metadata.get('booking_id')
            try:
                payment = Payment.objects.get(stripe_payment_intent_id=intent.id)
                payment.status = "succeeded"
                payment.save()
                # Optionally confirm booking
                booking = payment.booking
                booking.status = "confirmed"
                booking.save()
            except Payment.DoesNotExist:
                pass

        elif event['type'] == 'payment_intent.payment_failed':
            intent = event['data']['object']
            try:
                payment = Payment.objects.get(stripe_payment_intent_id=intent.id)
                payment.status = "failed"
                payment.save()
            except Payment.DoesNotExist:
                pass

        return Response(status=200)

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