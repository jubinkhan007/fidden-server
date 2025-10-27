# payments/tasks.py

from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from accounts.models import User
from api.utils.fcm import notify_user
from payments.models import Booking
from subscriptions.models import ShopSubscription, SubscriptionPlan
from .utils.helper_function import send_booking_reminder_email
import logging
import traceback
from django.db.models import Max, OuterRef, Subquery
from django.db import transaction

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="payments.tasks.complete_past_bookings", max_retries=3, default_retry_delay=60)
def complete_past_bookings(self):
    """
    Mark bookings as 'completed' if their appointment time has finished.

    Rules:
    - We only touch future/active bookings (status 'active' or 'confirmed').
    - We SKIP cancelled / no-show / already completed.
    - We consider the booking "finished" if:
        - the SlotBooking start_time is in the past AND
        - (if we have the actual Slot end_time) that end_time is also in the past.
    """

    now = timezone.now()

    # Pull candidate bookings:
    #   - "active" or "confirmed" are what we consider upcoming/ongoing
    #   - and the SlotBooking start_time is already in the past
    #   - exclude anything that's already terminal
    candidates = (
        Booking.objects
        .select_related("slot", "slot__slot")  # slot=SlotBooking, slot__slot=api.Slot
        .filter(
            status__in=["active", "confirmed"],
            slot__start_time__lte=now,
        )
        .exclude(status__in=["cancelled", "no-show", "completed"])
    )

    updated = 0

    for b in candidates:
        slot_booking = b.slot                 # SlotBooking
        real_slot    = getattr(slot_booking, "slot", None)  # api.Slot or None

        # Decide if it's actually over.
        # Prefer real end_time if we have it. If not, fall back to "start_time has passed".
        ended = False
        if real_slot and getattr(real_slot, "end_time", None):
            if real_slot.end_time <= now:
                ended = True
        else:
            # no explicit end_time available, so assume that if the start_time is past,
            # the service is now done (this is a fallback).
            if slot_booking.start_time <= now:
                ended = True

        if not ended:
            continue  # still in the future or in-progress

        # Mark completed atomically so we don't double-write in concurrent runs
        with transaction.atomic():
            # Re-check row in DB (avoid race if status changed in between)
            fresh = (
                Booking.objects
                .select_for_update()
                .filter(id=b.id)
                .exclude(status__in=["cancelled", "no-show", "completed"])
                .first()
            )
            if not fresh:
                continue

            fresh.status = "completed"
            # Only save the fields that changed; if you DO have updated_at, include it
            try:
                fresh.save(update_fields=["status", "updated_at"])
            except Exception:
                # If Booking doesn't actually have updated_at, fall back safely
                fresh.save(update_fields=["status"])

            updated += 1
            logger.info("Booking %s marked as completed", fresh.id)

    return f"{updated} bookings completed"





@shared_task
def send_booking_reminders():
    """
    Send reminders to users for their active bookings:
    - 1 day before
    - 1 hour before
    - 15 minutes before
    """
    now = timezone.now()

    try:
        bookings = Booking.objects.filter(status="active").select_related("slot", "user", "shop")

        reminders_sent = 0

        for booking in bookings:
            slot_end = booking.slot.end_time
            slot_start = booking.slot.start_time

            # Check if the booking is still in the future
            if slot_start <= now:
                continue

            reminder_times = {
                "1_day": slot_start - timedelta(days=1),
                "1_hour": slot_start - timedelta(hours=1),
                "15_minutes": slot_start - timedelta(minutes=15),
            }

            for reminder_label, reminder_time in reminder_times.items():
                # Allow a 1 minute window to send the reminder
                if reminder_time <= now <= reminder_time + timedelta(minutes=1):
                    try:
                        send_booking_reminder_email(booking, reminder_label)
                        reminders_sent += 1
                    except Exception as e:
                        logger.error(
                            "Failed to send booking reminder for Booking %s (%s): %s\n%s",
                            booking.id,
                            reminder_label,
                            str(e),
                            traceback.format_exc()
                        )

        return f"{reminders_sent} booking reminders sent."
    except Exception as e:
        logger.error("Error in send_booking_reminders task: %s\n%s", str(e), traceback.format_exc())
        return "Booking reminder task failed."

# payments/tasks.py
@shared_task
def send_smart_rebooking_prompts():
    """
    Analyzes booking history and sends notifications to users when it's
    time to rebook, based on their last completed appointment.
    """
    logger.info("Running smart rebooking prompts task...")

    # --- Configuration ---
    REBOOKING_CADENCE_DAYS = 30 # Default: prompt if last completed booking was > 30 days ago
    NOTIFICATION_TYPE = "rebooking_prompt" # For DB and push data

    # --- Logic ---
    now = timezone.now()
    rebooking_threshold_date = now - timedelta(days=REBOOKING_CADENCE_DAYS)
    sent_count = 0

    # 1. Find the most recent completed booking date for each user
    latest_completed_subquery = Booking.objects.filter(
        user=OuterRef('pk'),
        status='completed'
    ).order_by('-created_at').values('created_at')[:1]

    # 2. Find users whose latest completed booking is older than the threshold
    users_to_prompt_qs = User.objects.annotate(
        last_completed_booking_date=Subquery(latest_completed_subquery)
    ).filter(
        last_completed_booking_date__isnull=False,
        last_completed_booking_date__lt=rebooking_threshold_date
    )

    # 3. Exclude users who already have an upcoming active booking
    users_with_upcoming_bookings = Booking.objects.filter(
        status='active',
        slot__start_time__gt=now # Check against slot start time
    ).values_list('user_id', flat=True).distinct()

    users_to_prompt = users_to_prompt_qs.exclude(id__in=users_with_upcoming_bookings)

    logger.info(f"Found {users_to_prompt.count()} potential users to prompt for rebooking.")

    # 4. For each eligible user, get their last completed service and send notification
    for user in users_to_prompt:
        # Get the details of their most recent completed booking
        latest_booking = Booking.objects.filter(
            user=user,
            status='completed'
        ).select_related('slot__service', 'shop').order_by('-created_at').first()

        if not latest_booking or not latest_booking.slot or not latest_booking.slot.service:
            logger.warning(f"Could not find valid last booking details for user {user.id}. Skipping.")
            continue

        service = latest_booking.slot.service
        shop = latest_booking.shop

        # Construct notification message
        title = "Time to Rebook Your Appointment!"
        message = (
            f"Ready for your next session of {service.title} at {shop.name}? "
            f"It's been a little while since your last visit. Book now to keep up the great work!"
        )
        push_data = {
            "type": NOTIFICATION_TYPE,
            "shop_id": str(shop.id),
            "service_id": str(service.id),
            "title": title, # Include title in data
            # Add deeplink info if available, e.g., to the service or shop page
            # "deeplink": f"fidden://service/{service.id}"
        }

        # Send notification (saves to DB and sends push)
        try:
            notify_user(
                user=user,
                message=message, # Use full message for DB/email, push uses body from data or this
                notification_type=NOTIFICATION_TYPE,
                data=push_data
            )
            sent_count += 1
            logger.info(f"Sent rebooking prompt for service '{service.title}' to user {user.id}")
            # Optional: Add a short delay between sends if needed
            # time.sleep(0.1)
        except Exception as e:
            logger.error(f"Failed to send rebooking prompt to user {user.id}: {e}", exc_info=True)

    logger.info(f"Finished smart rebooking task. Sent {sent_count} prompts.")
    return f"Sent {sent_count} rebooking prompts."


@shared_task
def send_auto_followups():
    """
    Sends follow-up notifications (review prompts) approx. 24 hours
    after a booking is marked as completed, if no review exists yet,
    AND the shop is on the Momentum or Icon plan.
    """
    logger.info("Running auto-followups task...")
    now = timezone.now()
    yesterday = (now - timedelta(days=1)).date()

    # --- 👇 MODIFIED QUERY ---
    # Find bookings completed within the target window for eligible shops
    completed_bookings = Booking.objects.select_related(
        'user',
        'shop',
        'shop__subscription__plan', # Include plan for filtering
        'slot__service'
    ).filter(
        status='completed',
        updated_at__date=yesterday,
        # Ensure shop has an active subscription on Momentum or Icon
        shop__subscription__status=ShopSubscription.STATUS_ACTIVE,
        shop__subscription__plan__name__in=[SubscriptionPlan.MOMENTUM, SubscriptionPlan.ICON]
    ).exclude(
        review__isnull=False # Exclude bookings that already have a review
    )
    # --- END MODIFIED QUERY ---

    sent_count = 0
    sms_sent_count = 0
    email_sent_count = 0

    if not completed_bookings.exists():
        logger.info("No bookings found needing a follow-up for Momentum/Icon shops.")
        return "No eligible bookings found for follow-up."

    logger.info(f"Found {completed_bookings.count()} completed bookings for Momentum/Icon shops needing follow-up.")

    for booking in completed_bookings:
        user = booking.user
        shop = booking.shop
        service = booking.slot.service # Access service via slot relationship

        if not user or not shop or not service:
            logger.warning(f"Skipping follow-up for booking {booking.id} due to missing related data.")
            continue

        # --- Construct Messages (No changes needed here) ---
        title = f"How was your {service.title} at {shop.name}?"
        message_body = (
            f"Hi {user.name or 'there'},\n\n"
            f"We hope you enjoyed your recent {service.title} appointment at {shop.name}! "
            f"Your feedback helps us improve. Would you mind leaving a quick review?"
        )
        push_body = f"Enjoyed your {service.title} at {shop.name}? Tap to leave a review!"
        push_data = {
            "type": "review_request", "booking_id": str(booking.id),
            "shop_id": str(shop.id), "service_id": str(service.id),
            "title": title,
        }

        # --- Send Email (No changes needed here) ---
        email = getattr(user, "email", None)
        # ... (email sending logic) ...

        # --- Send SMS (No changes needed here) ---
        phone_number = getattr(user, 'mobile_number', None)
        # ... (SMS sending logic) ...

        # --- Save to DB Notification & Send Push (No changes needed here) ---
        try:
            notify_user(
                user=user, message=message_body,
                notification_type="review_request",
                data={**push_data, "body_override": push_body}
            )
            sent_count += 1
        except Exception as e:
            logger.error(f"[Followup] Failed to save/send push for booking {booking.id} to user {user.id}: {e}", exc_info=True)

    logger.info(f"Finished auto-followups task. Sent {sent_count} push/DB notifications, {email_sent_count} emails, {sms_sent_count} SMS.")
    return f"Sent {sent_count} push/DB, {email_sent_count} emails, {sms_sent_count} SMS."


@shared_task
def reengage_ghost_clients():
    """
    Identifies inactive users and sends them targeted promotions to re-engage them.
    """
    logger.info("Running ghost client re-engagement task...")
    # Example: Find users who haven't booked in the last 90 days
    ninety_days_ago = timezone.now() - timedelta(days=90)
    active_users = Booking.objects.filter(
        created_at__gte=ninety_days_ago
    ).values_list('user_id', flat=True)

    ghost_users = User.objects.exclude(id__in=active_users)

    for user in ghost_users:
        notify_user(
            user,
            "We miss you!",
            "It's been a while! Come back and enjoy a 10% discount on your next booking.",
            data={"discount_code": "COMEBACK10"}
        )
    logger.info(f"Sent {ghost_users.count()} re-engagement notifications.")