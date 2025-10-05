<<<<<<< HEAD
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.conf import settings
import stripe
from .models import Payment
from api.models import SlotBooking

stripe.api_key = settings.STRIPE_SECRET_KEY
endpoint_secret = settings.STRIPE_ENDPOINT_SECRET

@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    endpoint_secret = settings.STRIPE_ENDPOINT_SECRET

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)

    if event["type"] == "payment_intent.succeeded":
        intent = event["data"]["object"]
        booking_id = intent["metadata"].get("booking_id")
        try:
            payment = Payment.objects.get(stripe_payment_intent_id=intent["id"])
            payment.status = "succeeded"
            payment.save()
            # Update booking status
            booking = SlotBooking.objects.get(id=booking_id)
            booking.status = "confirmed"
            booking.save()
        except Payment.DoesNotExist:
            pass

    elif event["type"] == "payment_intent.payment_failed":
        intent = event["data"]["object"]
        try:
            payment = Payment.objects.get(stripe_payment_intent_id=intent["id"])
            payment.status = "failed"
            payment.save()
        except Payment.DoesNotExist:
            pass

    return JsonResponse({"status": "success"}, status=200)
=======
# # payments/webhook.py

# import logging
# from decimal import Decimal
# from django.views.decorators.csrf import csrf_exempt
# from django.http import JsonResponse, HttpResponse
# from django.conf import settings
# from django.utils import timezone
# import stripe

# from subscriptions.models import SubscriptionPlan, ShopSubscription   # <- import your subs models
# from api.models import Shop
# from .models import Payment
# from api.models import SlotBooking

# log = logging.getLogger(__name__)
# stripe.api_key = settings.STRIPE_SECRET_KEY

# FOUNDATION_NAME = getattr(SubscriptionPlan, "FOUNDATION", "Foundation")

# def _plan_by_price_id(price_id: str) -> SubscriptionPlan | None:
#     if not price_id:
#         return None
#     return SubscriptionPlan.objects.filter(stripe_price_id=price_id).first()

# def _ensure_foundation() -> SubscriptionPlan:
#     return (SubscriptionPlan.objects.filter(name__iexact=FOUNDATION_NAME).first()
#             or SubscriptionPlan.objects.order_by("id").first())

# def _status_from_stripe(s: str) -> str:
#     # map Stripe statuses to your internal ShopSubscription statuses if needed
#     # keep as-is if you already store stripe status verbatim
#     return s or ShopSubscription.STATUS_ACTIVE

# def _update_shop_subscription_from_stripe(shop: Shop, sub_obj: dict):
#     """
#     sub_obj is a stripe.Subscription dict (ideally with items.data.price expanded)
#     """
#     stripe_status = sub_obj.get("status", "active")
#     current_period_end = sub_obj.get("current_period_end")
#     cancel_at_period_end = bool(sub_obj.get("cancel_at_period_end"))
#     subscription_id = sub_obj.get("id")

#     # Grab the base recurring item → price id
#     items = (sub_obj.get("items") or {}).get("data") or []
#     price_id = None
#     for it in items:
#         p = (it.get("price") or {})
#         if p.get("type") == "recurring":
#             price_id = p.get("id")
#             break

#     plan = _plan_by_price_id(price_id) or _ensure_foundation()

#     end_dt = None
#     if current_period_end:
#         end_dt = timezone.datetime.fromtimestamp(int(current_period_end), tz=timezone.utc)

#     shop_sub, _ = ShopSubscription.objects.get_or_create(shop=shop)
#     shop_sub.plan = plan
#     shop_sub.status = _status_from_stripe(stripe_status)
#     shop_sub.stripe_subscription_id = subscription_id
#     shop_sub.start_date = shop_sub.start_date or timezone.now()
#     shop_sub.end_date = end_dt
#     shop_sub.cancel_at_period_end = cancel_at_period_end  # add field if you track it
#     shop_sub.save()
#     log.info("Updated ShopSubscription for shop=%s to plan=%s (stripe=%s)",
#              shop.id, plan.name, stripe_status)

# @csrf_exempt
# def stripe_webhook(request):
#     payload = request.body
#     sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
#     secret = getattr(settings, "STRIPE_ENDPOINT_SECRET", None)
#     if not secret:
#         log.error("STRIPE_ENDPOINT_SECRET not set.")
#         return HttpResponse(status=500)
#     if not sig_header:
#         log.warning("Missing Stripe-Signature header.")
#         return HttpResponse(status=400)

#     try:
#         event = stripe.Webhook.construct_event(payload, sig_header, secret)
#     except Exception as e:
#         log.warning("Stripe signature verification failed: %s", e)
#         return HttpResponse(status=400)

#     etype = event.get("type")
#     data = event.get("data", {}).get("object", {})

#     try:
#         # -----------------------------
#         # PAYMENTS (your existing code)
#         # -----------------------------
#         if etype == "payment_intent.succeeded":
#             intent = data
#             booking_id = (intent.get("metadata") or {}).get("booking_id")
#             try:
#                 payment = Payment.objects.get(stripe_payment_intent_id=intent["id"])
#                 payment.status = "succeeded"
#                 payment.save()
#                 if booking_id:
#                     try:
#                         booking = SlotBooking.objects.get(id=booking_id)
#                         booking.status = "confirmed"
#                         booking.save()
#                     except SlotBooking.DoesNotExist:
#                         log.warning("Booking id %s not found.", booking_id)
#             except Payment.DoesNotExist:
#                 log.warning("Payment with PI %s not found.", intent["id"])

#         elif etype == "payment_intent.payment_failed":
#             intent = data
#             try:
#                 payment = Payment.objects.get(stripe_payment_intent_id=intent["id"])
#                 payment.status = "failed"
#                 payment.save()
#             except Payment.DoesNotExist:
#                 log.warning("Payment with PI %s not found (failed).", intent["id"])

#         # ---------------------------------------
#         # SUBSCRIPTIONS (new: make plan changes)
#         # ---------------------------------------
#         elif etype == "checkout.session.completed":
#             # Only care when this was a subscription checkout
#             if data.get("mode") == "subscription":
#                 subscription_id = data.get("subscription")
#                 client_ref = data.get("client_reference_id")  # you set this to shop.id
#                 customer_id = data.get("customer")

#                 # Find the shop
#                 try:
#                     shop = Shop.objects.get(id=client_ref)
#                 except Shop.DoesNotExist:
#                     log.error("Shop %s not found from client_reference_id.", client_ref)
#                     return JsonResponse({"received": True})

#                 # Pull full subscription with price data
#                 sub = stripe.Subscription.retrieve(
#                     subscription_id,
#                     expand=["items.data.price"]
#                 )
#                 _update_shop_subscription_from_stripe(shop, sub)

#         elif etype == "customer.subscription.created" or etype == "customer.subscription.updated":
#             # When Stripe changes the items/status (upgrade/downgrade, past_due, pause, etc.)
#             sub = data  # already a subscription object
#             # We need to find the shop for this customer/subscription.
#             # Option A: save mapping shop.subscription.stripe_subscription_id so we can find Shop by it.
#             shop_sub = ShopSubscription.objects.filter(stripe_subscription_id=sub.get("id")).select_related("shop").first()
#             if not shop_sub:
#                 # Fallback: if you have user.customer mapping, resolve user->shop here
#                 log.info("Subscription id %s not yet mapped; skipping.", sub.get("id"))
#                 return JsonResponse({"received": True})

#             # Ensure we have price info; if not, retrieve expanded
#             if not ((sub.get("items") or {}).get("data") or []):
#                 sub = stripe.Subscription.retrieve(sub.get("id"), expand=["items.data.price"])
#             _update_shop_subscription_from_stripe(shop_sub.shop, sub)

#         elif etype == "customer.subscription.deleted":
#             # Immediate cancel → move to Foundation
#             sub = data
#             shop_sub = ShopSubscription.objects.filter(stripe_subscription_id=sub.get("id")).select_related("shop").first()
#             if shop_sub:
#                 foundation = _ensure_foundation()
#                 shop_sub.plan = foundation
#                 shop_sub.status = ShopSubscription.STATUS_ACTIVE
#                 shop_sub.stripe_subscription_id = None
#                 shop_sub.start_date = timezone.now()
#                 shop_sub.end_date = None
#                 shop_sub.cancel_at_period_end = False
#                 shop_sub.save()
#                 log.info("Subscription deleted; downgraded shop=%s to Foundation.", shop_sub.shop_id)

#         # Always ack
#         return JsonResponse({"received": True})
#     except Exception as e:
#         log.exception("Error handling %s: %s", etype, e)
#         # Acknowledge to avoid endless retries; log gives you details
#         return JsonResponse({"received": True})
>>>>>>> main
