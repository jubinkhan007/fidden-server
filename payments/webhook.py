from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.conf import settings
import stripe
from .models import Payment
from api.models import SlotBooking

stripe.api_key = settings.STRIPE_SECRET_KEY
endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

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
