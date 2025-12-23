# payments/tasks.py

from celery import shared_task
from django.utils import timezone
from datetime import datetime, timedelta
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
    Mark bookings as 'completed' once the appointment's effective end-time has passed.

    Priority for end-time:
      1) SlotBooking.end_time (instance-specific)
      2) SlotBooking.start_time + duration (SlotBooking.duration_minutes or service.duration or 30)
      3) LAST RESORT: treat start_time as end (legacy fallback)
    """
    from payments.models import Booking  # adjust import if your Booking model lives elsewhere

    now = timezone.now()

    candidates = (
        Booking.objects
        .select_related("slot", "slot__service")  # prefer service over slot__slot
        .filter(
            status__in=["active", "confirmed"],
            slot__start_time__lte=now,  # already started
        )
        .exclude(status__in=["cancelled", "no-show", "completed"])
    )

    def _effective_end(b) -> "datetime":
        sb = b.slot  # SlotBooking
        # 1) explicit instance end
        if getattr(sb, "end_time", None):
            return sb.end_time

        # try to derive a duration (minutes)
        duration = (
            getattr(sb, "duration_minutes", None)
            or getattr(sb, "duration", None)  # sometimes stored as 'duration'
            or getattr(getattr(sb, "service", None), "duration_minutes", None)
            or getattr(getattr(sb, "service", None), "duration", None)
            or 30  # sensible default
        )
        try:
            duration = int(duration)
        except Exception:
            duration = 30

        # 2) compute from start + duration
        if getattr(sb, "start_time", None):
            return sb.start_time + timedelta(minutes=duration)

        # 3) legacy fallback (should rarely hit)
        # if we somehow do not have start_time, return 'now' so it won’t flip early
        return now

    updated = 0
    for b in candidates:
        end_dt = _effective_end(b)
        if end_dt > now:
            continue  # appointment not finished yet

        with transaction.atomic():
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
            # Save minimally; include updated_at if present
            try:
                fresh.save(update_fields=["status", "updated_at"])
            except Exception:
                fresh.save(update_fields=["status"])
            updated += 1
            logger.info("Booking %s marked as completed (end=%s)", fresh.id, end_dt.isoformat())

    msg = f"{updated} bookings completed"
    logger.info(msg)
    return msg


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


@shared_task(name="api.tasks.send_auto_followups")
def send_auto_followups():
    """
    Sends follow-up notifications (review prompts) approx. 24 hours
    after a booking is marked as completed.
    
    V1 SPAM FIX:
    - Only sends if review_request_sent_at is NULL
    - Checks if review already exists using booking.review (OneToOne)
    - Sets review_request_sent_at after sending
    - Hard limit: 1 initial request per booking
    """
    logger.info("Running auto-followups task...")
    now = timezone.now()
    yesterday = (now - timedelta(days=1)).date()

    # Find bookings:
    # - Completed yesterday
    # - On Momentum/Icon plan
    # - review_request_sent_at is NULL (NOT SENT YET)
    # - No review linked to this booking (using OneToOne 'review' relation)
    completed_bookings = Booking.objects.select_related(
        'user',
        'shop',
        'shop__subscription__plan',
        'slot__service'
    ).filter(
        status='completed',
        updated_at__date=yesterday,
        shop__subscription__status=ShopSubscription.STATUS_ACTIVE,
        shop__subscription__plan__name__in=[SubscriptionPlan.MOMENTUM, SubscriptionPlan.ICON],
        review_request_sent_at__isnull=True,  # <-- IDEMPOTENCY CHECK
        review__isnull=True,  # <-- CORRECT: No RatingReview linked to this booking
    )

    sent_count = 0

    if not completed_bookings.exists():
        logger.info("No bookings found needing a follow-up.")
        return "No eligible bookings found for follow-up."

    logger.info(f"Found {completed_bookings.count()} completed bookings needing follow-up.")

    for booking in completed_bookings:
        user = booking.user
        shop = booking.shop
        service = booking.slot.service if booking.slot else None

        if not user or not shop or not service:
            logger.warning(f"Skipping follow-up for booking {booking.id} due to missing related data.")
            continue
        
        # DOUBLE CHECK: Skip if review already exists (belt and suspenders)
        if hasattr(booking, 'review') and booking.review is not None:
            logger.info(f"Skipping booking {booking.id} - review already exists")
            continue
        
        # SKIP if already sent (safety check)
        if booking.review_request_sent_at is not None:
            logger.info(f"Skipping booking {booking.id} - review request already sent")
            continue

        title = f"How was your {service.title} at {shop.name}?"
        message_body = (
            f"Hi {user.name or 'there'},\n\n"
            f"We hope you enjoyed your recent {service.title} appointment at {shop.name}! "
            f"Your feedback helps us improve. Would you mind leaving a quick review?"
        )
        push_body = f"Enjoyed your {service.title} at {shop.name}? Tap to leave a review!"
        push_data = {
            "type": "review_request",
            "booking_id": str(booking.id),
            "shop_id": str(shop.id),
            "service_id": str(service.id),
            "title": title,
        }

        try:
            notify_user(
                user=user,
                message=message_body,
                notification_type="review_request",
                data={**push_data, "body_override": push_body}
            )
            
            # MARK AS SENT - prevents duplicate sends
            booking.review_request_sent_at = now
            booking.save(update_fields=['review_request_sent_at'])
            
            sent_count += 1
            logger.info(f"[Followup] Sent review request for booking {booking.id}")
            
        except Exception as e:
            logger.error(f"[Followup] Failed for booking {booking.id}: {e}", exc_info=True)

    logger.info(f"Finished auto-followups task. Sent {sent_count} notifications.")
    return f"Sent {sent_count} review requests."


@shared_task(name="api.tasks.send_review_reminders")
def send_review_reminders():
    """
    Sends ONE reminder 48-72 hours after the initial review request,
    if no review has been submitted.
    
    V1 Rule: Maximum 2 notifications per booking (initial + reminder)
    
    RUNS EVERY 2 HOURS to catch the 48-72h window accurately.
    """
    logger.info("Running review reminders task...")
    now = timezone.now()
    
    # Window: 48-72 hours after initial request was sent
    reminder_window_start = now - timedelta(hours=72)
    reminder_window_end = now - timedelta(hours=48)

    # Find bookings:
    # - Initial review request was sent (within 48-72 hour window)
    # - Reminder NOT sent yet
    # - No review submitted (using OneToOne 'review' relation)
    eligible_bookings = Booking.objects.select_related(
        'user',
        'shop',
        'slot__service'
    ).filter(
        status='completed',
        review_request_sent_at__gte=reminder_window_start,
        review_request_sent_at__lte=reminder_window_end,
        review_reminder_sent_at__isnull=True,  # Reminder not sent yet
        review__isnull=True,  # <-- CORRECT: No review linked to this booking
    )

    sent_count = 0

    if not eligible_bookings.exists():
        logger.info("No bookings found needing a review reminder.")
        return "No eligible bookings found for reminder."

    logger.info(f"Found {eligible_bookings.count()} bookings eligible for review reminder.")

    for booking in eligible_bookings:
        user = booking.user
        shop = booking.shop
        service = booking.slot.service if booking.slot else None

        if not user or not shop or not service:
            continue
        
        # DOUBLE CHECK: Skip if review already exists
        if hasattr(booking, 'review') and booking.review is not None:
            logger.info(f"Skipping reminder for booking {booking.id} - review already exists")
            continue
        
        # SKIP if reminder already sent
        if booking.review_reminder_sent_at is not None:
            continue

        title = f"Last chance to review {shop.name}!"
        message_body = (
            f"Hi {user.name or 'there'},\n\n"
            f"Just a friendly reminder - we'd love to hear about your {service.title} experience at {shop.name}. "
            f"Your review helps other customers and supports {shop.name}!"
        )
        push_data = {
            "type": "review_reminder",
            "booking_id": str(booking.id),
            "shop_id": str(shop.id),
            "service_id": str(service.id),
            "title": title,
        }

        try:
            notify_user(
                user=user,
                message=message_body,
                notification_type="review_reminder",
                data=push_data
            )
            
            # MARK REMINDER AS SENT - this is the final notification
            booking.review_reminder_sent_at = now
            booking.save(update_fields=['review_reminder_sent_at'])
            
            sent_count += 1
            logger.info(f"[Reminder] Sent review reminder for booking {booking.id}")
            
        except Exception as e:
            logger.error(f"[Reminder] Failed for booking {booking.id}: {e}", exc_info=True)

    logger.info(f"Finished review reminders task. Sent {sent_count} reminders.")
    return f"Sent {sent_count} review reminders."


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