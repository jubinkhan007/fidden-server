# api/tasks.py
import logging
from datetime import datetime, timedelta
from django.utils import timezone
from django.conf import settings
from celery import shared_task
from django.core.mail import send_mail
from django.db.models import Count, Avg, Sum, F
from payments.models import Booking
from .models import AutoFillLog, Notification, PerformanceAnalytics, Revenue, Service, Slot, SlotBooking, Shop
from api import models
from .utils.fcm import notify_user
from subscriptions.models import SubscriptionPlan
from django.db import transaction
from django.contrib.auth import get_user_model
import time, uuid, json
from django.utils.timezone import now as tz_now


logger = logging.getLogger(__name__)

def _aware(dt):
    """Ensure datetime is timezone-aware."""
    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt


# api/tasks.py
from django.utils import timezone
from django.db.models import Q
from subscriptions.models import SubscriptionPlan, ShopSubscription

@shared_task(name="api.tasks.generate_weekly_ai_reports")
def generate_weekly_ai_reports():
    """
    Generates and delivers a weekly performance report for each shop
    that has an active AI assistant (either included or as an add-on).
    """
    logger.info("Starting weekly AI report generation...")
    end_date = timezone.now()
    start_date = end_date - timedelta(days=7)

    # All shops with active AI (addon or included in plan)
    eligible_shops = (
        Shop.objects.filter(
            Q(subscription__has_ai_addon=True) |
            Q(subscription__plan__ai_assistant=SubscriptionPlan.AI_INCLUDED),
            subscription__status=ShopSubscription.STATUS_ACTIVE,
            subscription__end_date__gt=timezone.now(),
        )
        .distinct()
        .select_related("subscription", "subscription__plan", "owner")
    )

    if not eligible_shops.exists():
        logger.info("No shops eligible for AI reports this week.")
        return

    for shop in eligible_shops.iterator():
        # 1) Weekly bookings
        weekly_bookings = Booking.objects.filter(
            shop=shop,
            created_at__range=(start_date, end_date),
        )
        completed_bookings = weekly_bookings.filter(status='completed')

        # 2) Core metrics
        total_appointments = completed_bookings.count()
        total_revenue = (
            completed_bookings.aggregate(total=Sum('payment__amount'))['total'] or 0
        )

        # 3) No-shows filled (by your AutoFillLog)
        no_shows_filled = AutoFillLog.objects.filter(
            shop=shop,
            created_at__range=(start_date, end_date),
            status='completed',  # adjust if you instead check filled_by_booking__isnull=False
        ).count()

        # 4) Top service (store as text in CharField)
        top_service_name = None
        top_service_count = 0
        top_service_data = (
            completed_bookings.values('slot__service_id')
            .annotate(count=Count('id'))
            .order_by('-count')
            .first()
        )
        if top_service_data and top_service_data['slot__service_id']:
            svc = Service.objects.filter(id=top_service_data['slot__service_id']).first()
            if svc:
                top_service_name = svc.title
                top_service_count = top_service_data['count']

        # 5) Persist analytics (now includes your new fields)
        analytics, _ = PerformanceAnalytics.objects.update_or_create(
            shop=shop,
            defaults={
                'total_revenue': total_revenue,
                'total_bookings': total_appointments,
                'no_shows_filled': no_shows_filled,
                'top_service': top_service_name,           # <- string, not model
                'week_start_date': start_date.date(),
                'updated_at': timezone.now(),
            },
        )
        logger.info(f"Generated AI report for {shop.name}")

        # 6) Build message lines directly (no helper methods required)
        # next-week forecast
        next_week_open_slots = Slot.objects.filter(
            shop=shop,
            start_time__gt=end_date,
            start_time__lte=end_date + timedelta(days=7),
            capacity_left__gt=0,
        ).count()

        top_service_line = (
            f"📈 Your most popular service was {top_service_name} with {top_service_count} bookings."
            if top_service_name else
            "📈 No standout service this week — let’s drive more bookings!"
        )
        forecast_line = f"🗓️ You’ve got {next_week_open_slots} open slots next week—let’s get them filled!"
        nudge_line = "You're building something great. Let's keep the momentum going! 💪"

        report_title = "Your Weekly Business Snapshot ✨"
        push_summary = (
            f"Your report is in! You earned ${total_revenue:.2f} and filled {no_shows_filled} no-shows."
        )

        detailed_message = (
            f"Here's your weekly wrap-up from your AI partner, {shop.ai_partner_name or 'Amara'}!\n\n"
            f"✅ You completed {total_appointments} appointments, earning ${total_revenue:.2f}.\n"
            f"🎯 You automatically filled {no_shows_filled} no-show slots!\n"
            f"{top_service_line}\n"
            f"{forecast_line}\n\n"
            f"{nudge_line}"
        )

        # 7) Deliver
        Notification.objects.create(
            recipient=shop.owner,
            message=detailed_message,
            notification_type="ai_report",
            data={"title": report_title},
        )
        notify_user(
    shop.owner,
    message=report_title,
    notification_type="ai_report",
    data={"summary": push_summary}
)
        send_mail(
            subject=f"[Fidden] {report_title}",
            message=detailed_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[shop.owner.email],
            fail_silently=False,
        )
        logger.info(f"Successfully sent report for {shop.name}")


# api/tasks.py
@shared_task(bind=True, name="api.tasks.trigger_no_show_auto_fill")
def trigger_no_show_auto_fill(self, booking_id):
    """
    When a booking is marked as no-show/late-cancel:
      1) Free capacity on the original slot
      2) Offer the SAME slot if its start_time is still in the future
      3) Otherwise, offer the next available future slot for the same service
    """
    from django.db import transaction
    from payments.models import Booking
    from api.models import Slot, SlotBooking, AutoFillLog, WaitlistEntry

    # -- Load booking & guardrails
    booking = (
        Booking.objects
        .select_related('shop', 'slot', 'slot__service', 'slot__slot')
        .filter(id=booking_id).first()
    )
    if not booking:
        logger.warning("[autofill] booking %s not found", booking_id)
        return "No booking."

    shop = booking.shop
    settings_obj = getattr(shop, 'ai_settings', None)
    if not settings_obj or not settings_obj.is_active:
        return "Auto-fill is not active for this shop."

    # -- Idempotency / race control
    with transaction.atomic():
        log, created = (
            AutoFillLog.objects
            .select_for_update()
            .get_or_create(
                original_booking=booking,
                defaults={"shop": shop, "status": "initiated"}
            )
        )
        if not created and log.status in ("queued", "initiated", "outreach_started", "completed"):
            logger.info("[autofill] already processing/finished for booking=%s; skipping", booking.id)
            return "Already processing"
        elif not created:
            log.status = "initiated"
            log.save(update_fields=["status"])

    # -- Ensure we can resolve SlotBooking and the real Slot
    slot_booking = booking.slot  # payments.Booking → api.SlotBooking
    if slot_booking is None:
        slot_booking = (
            SlotBooking.objects
            .select_related('slot', 'service')
            .filter(shop_id=booking.shop_id, start_time=booking.start_time)
            .first()
        )
        if slot_booking:
            Booking.objects.filter(id=booking.id).update(slot_id=slot_booking.id)
            logger.info("[autofill] repaired SlotBooking: booking=%s -> slot_booking=%s",
                        booking.id, slot_booking.id)
        else:
            AutoFillLog.objects.filter(original_booking=booking).update(status="no-slotbooking")
            return "No SlotBooking."

    service_id = slot_booking.service_id

    slot = slot_booking.slot  # the actual api.Slot
    if slot is None:
        slot = (
            Slot.objects
            .filter(
                shop_id=booking.shop_id,
                service_id=service_id,
                start_time=slot_booking.start_time
            ).first()
        )
        if slot:
            SlotBooking.objects.filter(id=slot_booking.id).update(slot_id=slot.id)
            logger.info("[autofill] repaired Slot on SlotBooking=%s -> slot=%s",
                        slot_booking.id, slot.id)
        else:
            AutoFillLog.objects.filter(original_booking=booking).update(status="no-slot")
            return "No Slot."

    # -- Free 1 capacity on the original slot
    Slot.objects.filter(id=slot.id).update(capacity_left=F('capacity_left') + 1)

    # -- Decide which slot to offer
    now = timezone.now()
    if slot.start_time and slot.start_time > now:
        # Original slot is still upcoming → offer it
        slot_for_offers = slot
    else:
        # Otherwise offer the earliest future slot for this service
        slot_for_offers = (
            Slot.objects
            .filter(
                shop=shop,
                service_id=service_id,
                start_time__gte=now,
                capacity_left__gt=0,
            )
            .order_by("start_time")
            .first()
        )
        if not slot_for_offers:
            # Nothing to offer—record & stop
            AutoFillLog.objects.filter(original_booking=booking).update(status='failed_no_future_slot')
            logger.info("[autofill] no future slot to offer for shop=%s service=%s", shop.id, service_id)
            return "No future slot."

    # -- Candidate selection (exclude original user, dedupe)
    qs = (
        WaitlistEntry.objects
        .filter(shop=shop, opted_in_offers=True)
        .select_related('user', 'service')
    )

    def _dedupe(seq):
        seen = set()
        out = []
        for x in seq:
            if x not in seen:
                out.append(x)
                seen.add(x)
        return out

    candidates = []
    for entry in qs:
        if entry.user_id == booking.user_id:
            continue  # don't ping the same user who just no-showed
        score = 5 if (service_id and entry.service_id == service_id) else 0
        candidates.append((entry.user_id, score))

    if not candidates:
        AutoFillLog.objects.filter(original_booking=booking).update(status='failed_no_candidates')
        return "No candidates."

    candidates.sort(key=lambda t: t[1], reverse=True)
    user_ids_ranked = _dedupe([uid for (uid, _) in candidates])
    top_ids  = user_ids_ranked[:5]
    next_ids = user_ids_ranked[5:25]

    logger.info(
        "[autofill] enqueue original_slot.id=%s offered_slot.id=%s slot_booking.id=%s service_id=%s",
        slot.id, slot_for_offers.id, slot_booking.id, service_id
    )

    # -- Outreach
    send_autofill_offers.delay(slot_for_offers.id, top_ids, "push")
    if next_ids:
        send_autofill_offers.apply_async(args=[slot_for_offers.id, next_ids, "email"], countdown=60)

    AutoFillLog.objects.filter(original_booking=booking).update(status='outreach_started')
    return "Outreach started."

# api/tasks.py
@shared_task(name="api.tasks.send_autofill_offers")
def send_autofill_offers(slot_id, user_ids, channel):
    """
    Sends notifications to a list of users for a specific Slot.
    slot_id must be api.models.Slot.pk. If a Slot isn't found, we try to
    interpret slot_id as a SlotBooking.pk and map to its Slot.
    """
    from .models import Slot, SlotBooking
    started_at = tz_now()
    t0 = time.monotonic()
    run_id = str(uuid.uuid4())[:8]

    def _dt(ms=0):
        return f"{int((time.monotonic() - t0) * 1000)}ms"

    def _safe(obj):
        try:
            return json.dumps(obj, ensure_ascii=False)
        except Exception:
            return str(obj)

    def _redact(email):
        if not email or "@" not in email:
            return email
        name, host = email.split("@", 1)
        return (name[:1] + "***@" + host)

    logger.info("[autofill:%s] start slot_id=%s users=%s channel=%s at=%s",
                run_id, slot_id, user_ids, channel, started_at.isoformat())

    # 1) Find the Slot (with defensive fallback)
    slot = None
    try:
        slot = Slot.objects.select_related('shop', 'service').get(id=slot_id)
        logger.info("[autofill:%s] %s found Slot id=%s shop=%s service=%s (%s)",
                    run_id, _dt(), slot.id, slot.shop_id, slot.service_id, slot.start_time.isoformat())
    except Slot.DoesNotExist:
        logger.warning("[autofill:%s] %s Slot id=%s not found; trying SlotBooking fallback",
                       run_id, _dt(), slot_id)
        sb = SlotBooking.objects.filter(id=slot_id).select_related("slot").first()
        if sb and sb.slot_id:
            slot = Slot.objects.select_related('shop', 'service').filter(id=sb.slot_id).first()
            logger.warning("[autofill:%s] %s slot_id looked like SlotBooking.id; mapped to slot_id=%s",
                           run_id, _dt(), getattr(slot, "id", None))

    if not slot:
        logger.warning("[autofill:%s] %s abort: no slot", run_id, _dt())
        return "No slot."

    # 2) Capacity guard
    cap = (slot.capacity_left or 0)
    logger.info("[autofill:%s] %s capacity_left=%s", run_id, _dt(), cap)
    if cap <= 0:
        logger.info("[autofill:%s] %s abort: slot filled", run_id, _dt())
        return "Slot was filled before this wave."

    # 3) Users via AUTH_USER_MODEL
    User = get_user_model()
    users_qs = User.objects.filter(id__in=user_ids).only("id", "email")
    users = list(users_qs)
    logger.info("[autofill:%s] %s matched_users=%d ids=%s",
                run_id, _dt(), len(users), [u.id for u in users])
    if not users:
        return "No recipients."

    # 4) Compose content (localize time for display + payload)
    start_local = timezone.localtime(slot.start_time)  # uses settings.TIME_ZONE
    human_time = start_local.strftime("%I:%M %p on %b %d")
    iso_local = start_local.isoformat()

    subject = "An opening just became available!"
    message_body = (
        f"{slot.shop.name} just had a {slot.service.title} spot open up at "
        f"{human_time}. First come, first served!"
    )
    shortlink = f"https://your-app.com/book/{slot.id}"
    full_message = f"{message_body}\n\nTap to book: {shortlink}"

    data = {
        "type": "autofill_offer",
        "action": "book_offer",
        "slot_id": str(slot.id),
        "shop_id": str(slot.shop_id),
        "service_id": str(slot.service_id),
        "serviceName": slot.service.title or "",
        "service_img": getattr(slot.service, "image_url", "") or "",
        "shopName": slot.shop.name or "",
        "shopAddress": getattr(slot.shop, "address", "") or "",
        "serviceDurationMinutes": str(getattr(slot.service, "duration", 0)),
        "start_time": iso_local,  # localized ISO for client rendering
        "price": str(getattr(slot.service, "price", 0) or 0),
        "discountPrice": str(getattr(slot.service, "discount_price", "") or ""),
        "deeplink": f"fidden://book/{slot.id}",
        "url": shortlink,
        "title": subject,
        "body": message_body,
    }
    logger.info("[autofill:%s] %s payload=%s", run_id, _dt(), _safe(data))

    # 5) Push + Email
    sent_push = 0
    sent_email = 0

    if channel in ("push", "sms_push", "email_push"):
        logger.info("[autofill:%s] %s entering push branch channel=%s",
                    run_id, _dt(), channel)
        for u in users:
            try:
                logger.debug("[autofill:%s] %s push→user_id=%s", run_id, _dt(), u.id)
                notify_user(
                    user=u,
                    message=message_body,
                    notification_type="autofill_offer",
                    data=data,
                    debug=True,
                    dry_run=False,
                )
                sent_push += 1
            except Exception as e:
                logger.warning("[autofill:%s] %s push failed user_id=%s err=%s",
                               run_id, _dt(), getattr(u, "id", None), e, exc_info=True)

    if channel in ("email", "email_push"):
        logger.info("[autofill:%s] %s entering email branch channel=%s",
                    run_id, _dt(), channel)
        for u in users:
            email = getattr(u, "email", None)
            logger.debug("[autofill:%s] %s email candidate user_id=%s email=%s",
                         run_id, _dt(), getattr(u, "id", None), _redact(email))
            if not email:
                continue
            try:
                send_mail(
                    subject=f"[Fidden] {subject}",
                    message=full_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=False,
                )
                sent_email += 1
                logger.debug("[autofill:%s] %s email sent user_id=%s email=%s",
                             run_id, _dt(), getattr(u, "id", None), _redact(email))
            except Exception as e:
                logger.warning("[autofill:%s] %s email failed user_id=%s email=%s err=%s",
                               run_id, _dt(), getattr(u, "id", None), _redact(email), e, exc_info=True)

    elapsed = _dt()
    logger.info("[autofill:%s] done elapsed=%s push_sent=%d email_sent=%d slot_id=%s",
                run_id, elapsed, sent_push, sent_email, slot.id)
    return f"push={sent_push}, email={sent_email}, recipients={len(users)}, channel={channel}"

@shared_task
def calculate_analytics():
    for shop in Shop.objects.all():
        bookings = Booking.objects.filter(shop=shop)
        total_bookings = bookings.count()

        # Basic Analytics
        total_revenue = shop.revenues.aggregate(total=Sum('revenue'))['total'] or 0 # Use Sum directly
        average_rating = shop.ratings.aggregate(avg=Avg('rating'))['avg'] or 0.0

        # Moderate Analytics
        cancellation_rate = (bookings.filter(status='cancelled').count() / total_bookings * 100) if total_bookings > 0 else 0

        # Advanced Analytics
        repeat_customer_rate = 0
        if total_bookings > 0:
            customer_counts = bookings.values('user').annotate(count=Count('id'))
            repeat_customers = sum(1 for c in customer_counts if c['count'] > 1)
            total_customers = len(customer_counts)
            repeat_customer_rate = (repeat_customers / total_customers * 100) if total_customers > 0 else 0

        top_service = bookings.values('slot__service__title').annotate(count=Count('id')).order_by('-count').first()
        peak_booking_time = bookings.values('slot__start_time__hour').annotate(count=Count('id')).order_by('-count').first()

        PerformanceAnalytics.objects.update_or_create(
            shop=shop,
            defaults={
                'total_revenue': total_revenue,
                'total_bookings': total_bookings,
                'average_rating': average_rating,
                'cancellation_rate': cancellation_rate,
                'repeat_customer_rate': repeat_customer_rate,
                'top_service': top_service['slot__service__title'] if top_service else None,
                'peak_booking_time': f"{peak_booking_time['slot__start_time__hour']}:00" if peak_booking_time else None,
            }
        )


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def prefill_slots(self, days_ahead=14):
    """
    Prefill slots for the next `days_ahead` days per shop/service.
    - Idempotent: fills missing slots instead of skipping whole days
    - Handles cross-month continuous slot creation
    - Always ensures coverage for `days_ahead` days from today
    """
    created_count = 0
    try:
        # --- CLEAN PREVIOUS / PAST SLOTS ---
        past_slots = Slot.objects.filter(end_time__lt=timezone.now()).filter(bookings__isnull=True)
        deleted_count, _ = past_slots.delete()
        if deleted_count:
            logger.info(f"[Prefill Slots] Deleted {deleted_count} past slots (without bookings).")

        # --- CREATE NEW SLOTS ---
        today = timezone.localdate()
        target_end = today + timedelta(days=days_ahead - 1)

        for shop in Shop.objects.prefetch_related("services").all():
            services = shop.services.filter(is_active=True)
            for service in services:
                start_date = today  # FIX: Always start from today
                end_date = target_end

                for offset in range((end_date - start_date).days + 1):
                    date = start_date + timedelta(days=offset)
                    weekday = date.strftime("%A").lower()

                    if (shop.close_days or []) and weekday in shop.close_days:
                        continue

                    duration = service.duration or 30
                    start_dt = timezone.make_aware(datetime.combine(date, shop.start_at), timezone.get_current_timezone())
                    end_dt = timezone.make_aware(datetime.combine(date, shop.close_at), timezone.get_current_timezone())
                    if end_dt <= start_dt:
                        continue

                    # Get existing start times for this shop/service/date
                    existing_times = set(
                        Slot.objects.filter(shop=shop, service=service, start_time__date=date)
                        .values_list("start_time", flat=True)
                    )

                    current = start_dt
                    batch = []
                    while current + timedelta(minutes=duration) <= end_dt:
                        if current not in existing_times:  # only add missing slots
                            batch.append(Slot(
                                shop=shop,
                                service=service,
                                start_time=current,
                                end_time=current + timedelta(minutes=duration),
                                capacity_left=service.capacity,
                            ))
                        current += timedelta(minutes=duration)

                    if batch:
                        Slot.objects.bulk_create(batch, ignore_conflicts=True)
                        created_count += len(batch)
                        logger.info(f"[Prefill Slots] Created {len(batch)} slots for {shop.name} / {service.title} on {date}")

        logger.info(f"[Prefill Slots] Created {created_count} slots across all shops/services.")
        return f"Prefilled {days_ahead} days with {created_count} slots."

    except Exception as e:
        logger.error(f"[Prefill Slots] Error: {e}", exc_info=True)
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def send_upcoming_slot_reminders(self, window_minutes=30):
    """Send reminders for upcoming confirmed bookings."""
    now = timezone.now()
    window_end = now + timedelta(minutes=window_minutes)
    try:
        upcoming = SlotBooking.objects.select_related("user", "service", "shop")\
            .filter(status="confirmed", start_time__gte=now, start_time__lte=window_end)
        sent_count = 0
        for b in upcoming:
            email = getattr(b.user, "email", None)
            if not email:
                continue
            subject = f"Reminder: {b.service.title} at {b.shop.name}"
            display_name = getattr(b.user, "name", None) or getattr(b.user, "email", "there")
            msg = (
                f"Dear {display_name},\n\nYour booking for {b.service.title} "
                f"starts at {timezone.localtime(b.start_time).strftime('%Y-%m-%d %H:%M')}.\n\nThank you!"
            )
            try:
                send_mail(subject, msg, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
                sent_count += 1
            except Exception as e:
                logger.warning(f"[Reminder] Failed to send to {email}: {e}")
        logger.info(f"[Reminder] Sent {sent_count} reminders for upcoming slots.")
        return f"Sent {sent_count} reminders."
    except Exception as e:
        logger.error(f"[Reminder Task] Error: {e}", exc_info=True)
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def cleanup_old_cancelled_bookings(self, days=7, batch_size=1000):
    """Cleanup old cancelled bookings, restore slot capacity."""
    try:
        cutoff = timezone.now() - timedelta(days=days)
        total_deleted = 0
        while True:
            old_bookings = SlotBooking.objects.select_for_update()\
                .filter(status="cancelled", start_time__lt=cutoff).order_by("id")[:batch_size]
            if not old_bookings.exists():
                break
            for booking in old_bookings:
                slot = booking.slot
                slot.capacity_left += 1
                slot.save(update_fields=['capacity_left'])
                booking.delete()
                total_deleted += 1
            if old_bookings.count() < batch_size:
                break
        logger.info(f"[Cleanup] Deleted {total_deleted} old cancelled bookings (older than {days} days).")
        return f"Deleted {total_deleted} old cancelled bookings."
    except Exception as e:
        logger.error(f"[Cleanup Task] Error: {e}", exc_info=True)
        raise self.retry(exc=e)

@shared_task
def auto_cancel_booking(booking_id):
    try:
        booking = SlotBooking.objects.select_related("slot", "shop").get(id=booking_id)
    except SlotBooking.DoesNotExist:
        logger.warning(f"Booking {booking_id} does not exist.")
        return f"Booking {booking_id} does not exist."

    if booking.payment_status == "pending" and booking.status != "cancelled":
        booking.status = "cancelled"
        booking.save(update_fields=["status"])
        logger.info(f"Booking {booking_id} auto-cancelled due to payment timeout.")

        if booking.slot.capacity_left is not None:
            booking.slot.capacity_left += 1
            booking.slot.save(update_fields=["capacity_left"])

        if booking.shop.capacity is not None:
            booking.shop.capacity += 1
            booking.shop.save(update_fields=["capacity"])

        return f"Booking {booking_id} auto-cancelled."

    logger.info(f"Booking {booking_id} not cancelled (already paid or cancelled).")
    return f"Booking {booking_id} not cancelled."