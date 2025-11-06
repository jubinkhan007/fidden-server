# api/tasks.py
from decimal import Decimal
import logging
from datetime import datetime, timedelta
from django.utils import timezone
from django.conf import settings
from celery import shared_task
from django.core.mail import send_mail
from django.db.models import Count, Avg, Sum, F
from api.utils.phones import get_user_phone
from api.utils.sms import send_sms
from api.utils.zapier import send_klaviyo_event
from payments.models import Booking, TransactionLog
from .models import AutoFillLog, Notification, PerformanceAnalytics, Revenue, Service, Slot, SlotBooking, Shop, WeeklySummary
from api import models
from .utils.fcm import notify_user, send_push_notification
from subscriptions.models import SubscriptionPlan
from django.db import transaction
from django.contrib.auth import get_user_model
import time, uuid, json
from django.utils.timezone import now as tz_now
from api.utils.sms import send_sms

logger = logging.getLogger(__name__)

def _aware(dt):
    """Ensure datetime is timezone-aware."""
    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt


# api/tasks.py
from django.utils import timezone
from django.db.models import Q
from subscriptions.models import SubscriptionPlan, ShopSubscription

# in api/tasks.py
@shared_task(name="api.tasks.generate_weekly_ai_reports", bind=True, max_retries=2, default_retry_delay=60)
def generate_weekly_ai_reports(self):
    logger.info("Starting weekly AI report generation...")

    end_dt = timezone.now()
    start_dt = end_dt - timedelta(days=7)

    prev_start = start_dt - timedelta(days=7)
    prev_end = start_dt

    eligible_shops = Shop.objects.select_related(
        "owner", "subscription", "subscription__plan"
    ).filter(
        # EITHER the plan includes AI (like Icon)
        Q(subscription__plan__ai_assistant=SubscriptionPlan.AI_INCLUDED) |
        # OR the user has purchased the AI add-on
        Q(subscription__has_ai_addon=True)
    ).distinct()
    if not eligible_shops.exists():
        logger.info("No shops eligible for AI reports this week.")
        return "No shops"

    for shop in eligible_shops.iterator():
        owner = shop.owner
        if not owner:
            continue

        #
        # 1. BOOKINGS THIS WEEK
        #
        paid_this_week = (
            Booking.objects
            .filter(
                shop=shop,
                status="completed",
                created_at__gte=start_dt,
                created_at__lte=end_dt,
            )
            .select_related("slot", "slot__service")  # slot is SlotBooking, slot.service is Service
        )

        total_appointments = paid_this_week.count()

        #
        # 2. REVENUE THIS WEEK (sum TransactionLog.payment-type rows for this shop in window)
        #
        total_revenue = (
            TransactionLog.objects
            .filter(
                shop=shop,
                transaction_type="payment",
                created_at__gte=start_dt,
                created_at__lte=end_dt,
            )
            .aggregate(s=Sum("amount"))["s"]
            or Decimal("0.00")
        )

        #
        # 3. PREVIOUS WEEK REVENUE (for growth_rate)
        #
        prev_revenue = (
            TransactionLog.objects
            .filter(
                shop=shop,
                transaction_type="payment",
                created_at__gte=prev_start,
                created_at__lte=prev_end,
            )
            .aggregate(s=Sum("amount"))["s"]
            or Decimal("0.00")
        )

        if prev_revenue > 0:
            growth_rate = float(((total_revenue - prev_revenue) / prev_revenue) * 100)
        else:
            growth_rate = 0.0

        #
        # 4. REBOOKING RATE
        #    % of unique clients from last 7 days who ALSO booked (completed) >=2 times in last 30 days
        #
        last_30 = end_dt - timedelta(days=30)

        clients_this_week = paid_this_week.values_list("user_id", flat=True).distinct()

        rebooked_clients = (
            Booking.objects
            .filter(
                shop=shop,
                status="completed",
                user_id__in=clients_this_week,
                created_at__gte=last_30,
                created_at__lte=end_dt,
            )
            .values("user_id")
            .annotate(c=Count("id"))
            .filter(c__gte=2)
            .count()
        )

        unique_clients = len(set(clients_this_week))
        rebooking_rate = (rebooked_clients / unique_clients * 100.0) if unique_clients else 0.0

        #
        # 5. NO-SHOW RECOVERY
        #
        no_shows_filled = (
            AutoFillLog.objects
            .filter(
                shop=shop,
                status="completed",
                created_at__gte=start_dt,
                created_at__lte=end_dt,
                filled_by_booking__isnull=False,
            )
            .values("filled_by_booking_id")
            .distinct()
            .count()
        )

        #
        # 6. TOP SERVICE
        #
        top_service_name = ""
        top_service_count = 0
        top_service_row = (
            paid_this_week
            .values("slot__service_id", "slot__service__title")
            .annotate(cnt=Count("id"))
            .order_by("-cnt")
            .first()
        )
        if top_service_row:
            top_service_name = top_service_row["slot__service__title"] or ""
            top_service_count = top_service_row["cnt"]

        #
        # 7. NEXT WEEK FORECAST
        #
        next_week_start = (end_dt + timedelta(days=1)).date()
        next_week_end = next_week_start + timedelta(days=6)

        open_slots_next_week = Slot.objects.filter(
            shop=shop,
            start_time__date__gte=next_week_start,
            start_time__date__lte=next_week_end,
            capacity_left__gt=0,
        ).count()

        avg_ticket = (total_revenue / total_appointments) if total_appointments else Decimal("0.00")
        forecast_estimated_revenue = avg_ticket * Decimal(open_slots_next_week)

        #
        # 8. COACHING TEXT / CTA CARDS
        #
        ai_motivation = (
            "You didn’t just serve clients — you built confidence and trust this week. "
            "Let’s carry that momentum into next week."
        )

        revenue_booster_text = (
            f"Promote your {top_service_name} first thing Monday. "
            f"It was booked {top_service_count} times this week and drove great reviews. "
            "Want me to generate an IG caption + booking link?"
            if top_service_name
            else
            "Promote your top service in Stories Monday morning. "
            "Ask people to DM you for a spot — I can draft the caption + link."
        )

        retention_play_text = (
            "Some clients haven’t rebooked yet. Offer them a ‘Next Week Loyalty Boost’ — "
            "10% off if they book within 7 days. Want me to prep that SMS blast?"
        )

        ai_recommendations = {
            "revenue_booster": {
                "headline": "Revenue Booster",
                "text": revenue_booster_text,
                "cta_label": "Yes, Create It",
                "cta_action": "generate_marketing_caption",
            },
            "retention_play": {
                "headline": "Retention Play",
                "text": retention_play_text,
                "cta_label": "Send via Email",
                "cta_action": "send_loyalty_email",   # <-- changed from send_loyalty_sms
            },
            "forecast": {
                "open_slots_next_week": open_slots_next_week,
                "forecast_estimated_revenue": float(forecast_estimated_revenue),
            },
        }

        #
        # 9. SAVE WeeklySummary
        #
        summary = WeeklySummary.objects.create(
            shop=shop,
            provider=owner,
            week_start_date=start_dt.date(),
            week_end_date=end_dt.date(),
            total_appointments=total_appointments,
            revenue_generated=total_revenue,
            rebooking_rate=rebooking_rate,
            growth_rate=growth_rate,
            no_shows_filled=no_shows_filled,
            top_service=top_service_name,
            top_service_count=top_service_count,
            open_slots_next_week=open_slots_next_week,
            forecast_estimated_revenue=forecast_estimated_revenue,
            ai_motivation=ai_motivation,
            ai_recommendations=ai_recommendations,
            delivered_channels=[],
        )

        deep_link = f"fidden://weekly-recap/{summary.id}"

        #
        # 10. APP NOTIFICATION + PUSH
        #
        report_title = "Your Weekly Business Snapshot ✨"
        push_summary = (
            f"Hey {getattr(owner, 'name', '') or ''} — you wrapped another great week. "
            f"${float(total_revenue):.2f} earned, {no_shows_filled} no-shows saved. "
            "Tap to see your gameplan."
        )

        detailed_message = (
            f"Here's your weekly wrap-up from your AI partner, "
            f"{shop.ai_partner_name or 'Amara'}!\n\n"
            f"✨ You served {total_appointments} clients this week.\n"
            f"💵 You earned ${float(total_revenue):.2f} in total bookings.\n"
            f"🔁 Rebooking rate: {rebooking_rate:.0f}%.\n"
            f"⏱ You filled {no_shows_filled} last-minute cancellations.\n"
            f"🗓 {open_slots_next_week} open slots next week.\n\n"
            "You’re not just running a business — you’re building a movement. "
            "Let’s make next week your strongest yet."
        )

        Notification.objects.create(
            recipient=owner,
            message=detailed_message,
            notification_type="ai_report",
            data={
                "title": report_title,
                "deep_link": deep_link,
                "weekly_summary_id": str(summary.id),
            },
        )

        try:
            notify_user(
                owner,
                message=report_title,
                notification_type="ai_report",
                data={
                    "summary": push_summary,
                    "deep_link": deep_link,
                    "weekly_summary_id": str(summary.id),
                },
            )
            delivered_channels = ["in_app", "push"]
        except Exception:
            logger.exception("notify_user failed for owner %s", owner.id)
            delivered_channels = ["in_app"]

        #
        # 11. EMAIL COPY
        #
        recipient_email = (getattr(owner, "email", "") or "").strip()
        if recipient_email:
            email_subject = f"[Fidden] {report_title}"
            email_body = (
                detailed_message
                + "\n\n"
                + ai_motivation
                + "\n\nRevenue Booster:\n- "
                + revenue_booster_text
                + "\n\nRetention Play:\n- "
                + retention_play_text
            )
            try:
                send_mail(
                    subject=email_subject,
                    message=email_body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[recipient_email],
                    fail_silently=False,
                )
                delivered_channels.append("email")
            except Exception:
                logger.exception("Failed to send weekly summary email to %s", recipient_email)

        summary.delivered_channels = delivered_channels
        summary.save(update_fields=["delivered_channels"])

        #
        # 12. PERFORMANCE ANALYTICS SNAPSHOT
        #
        PerformanceAnalytics.objects.update_or_create(
            shop=shop,
            defaults={
                "total_revenue": total_revenue,
                "total_bookings": total_appointments,
                "no_shows_filled": no_shows_filled,
                "top_service": top_service_name,
                "week_start_date": start_dt.date(),
                "updated_at": timezone.now(),
            },
        )

        #
        # 13. KLAVIYO EVENT ENRICHMENT
        #
        try:
            email_for_klaviyo = getattr(owner, "email", None)
            if email_for_klaviyo:
                profile_payload = {
                    "plan": getattr(
                        getattr(getattr(shop, "subscription", None), "plan", None),
                        "name",
                        None,
                    ),
                    "plan_status": getattr(
                        getattr(shop, "subscription", None),
                        "status",
                        None,
                    ),
                    "ai_addon": bool(
                        getattr(getattr(shop, "subscription", None), "ai_assistant", False)
                    ),
                    "shop_id": shop.id,
                }

                event_props = {
                    "shop_id": shop.id,
                    "weekly_summary_id": str(summary.id),
                    "week_start": str(start_dt.date()),
                    "week_end": str(end_dt.date()),
                    "total_appointments": total_appointments,
                    "total_revenue": float(total_revenue),
                    "growth_rate": growth_rate,
                    "rebooking_rate": rebooking_rate,
                    "no_shows_filled": no_shows_filled,
                    "top_service": top_service_name,
                    "top_service_count": top_service_count,
                    "open_slots_next_week": open_slots_next_week,
                    "forecast_estimated_revenue": float(forecast_estimated_revenue),
                    "ai_motivation": ai_motivation,
                    "ai_recommendations": ai_recommendations,
                    "deep_link": deep_link,
                }

                send_klaviyo_event(
                    email=email_for_klaviyo,
                    event_name="Weekly Recap Ready",
                    profile=profile_payload,
                    event_props=event_props,
                )
        except Exception:
            logger.exception("[klaviyo] weekly recap sync failed for shop %s", shop.id)

    logger.info("Finished weekly AI report generation for all shops.")
    return "ok"



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
    log.offered_slot = slot_for_offers
    log.save(update_fields=["offered_slot"])
    logger.info(
    "[autofill] log %s now has offered_slot.id=%s (original_booking=%s)",
    log.id, getattr(slot_for_offers, "id", None), booking.id
    )

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

    # 5) Push + Email + SMS
    sent_push = 0
    sent_email = 0
    sent_sms = 0

    # ❶ Persist a Notification for every user (no delivery here)
    for u in users:
        try:
            notify_user(
                user=u,
                message=message_body,
                notification_type="autofill_offer",
                data=data,
                debug=False,
                dry_run=True,  # persist only
            )
        except Exception as e:
            logger.warning("[autofill:%s] %s notify_user failed user_id=%s err=%s",
                           run_id, _dt(), getattr(u, "id", None), e, exc_info=True)

    # ❷ Push (deliver only when channel includes push)
    if channel in ("push", "sms_push", "email_push"):
        logger.info("[autofill:%s] %s entering push branch channel=%s", run_id, _dt(), channel)
        for u in users:
            try:
                send_push_notification(
                    user=u,
                    title=subject,
                    message=message_body,
                    data=data,
                    debug=False,
                    dry_run=False,
                )
                sent_push += 1
            except Exception as e:
                logger.warning("[autofill:%s] %s push failed user_id=%s err=%s",
                               run_id, _dt(), getattr(u, "id", None), e, exc_info=True)

        # ❸ SMS (deliver only when channel includes sms)
    if channel in ("sms", "sms_push", "email_sms", "all"):
            logger.info("[autofill:%s] %s entering sms branch channel=%s", run_id, _dt(), channel)
            for u in users:
                phone = get_user_phone(u)  # central helper
                if not phone:
                    logger.debug(
                        "[autofill:%s] %s user_id=%s has no phone number",
                        run_id, _dt(), getattr(u, "id", None)
                    )
                    continue

                sms_body = (
                    f"Fidden: Slot available! {slot.service.title} at {slot.shop.name} "
                    f"{human_time}. Book now: {shortlink}"
                )
                try:
                    if send_sms(phone, sms_body):
                        sent_sms += 1
                except Exception as e:
                    logger.warning(
                        "[autofill:%s] %s SMS failed user_id=%s phone=%s err=%s",
                        run_id, _dt(), getattr(u, "id", None), phone, e, exc_info=True
                    )


    # ❹ Email
    if channel in ("email", "email_push", "email_sms", "all"):
        logger.info("[autofill:%s] %s entering email branch channel=%s", run_id, _dt(), channel)
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
    logger.info("[autofill:%s] done elapsed=%s push_sent=%d sms_sent=%d email_sent=%d slot_id=%s",
                run_id, elapsed, sent_push, sent_sms, sent_email, slot.id)
    return f"push={sent_push}, sms={sent_sms}, email={sent_email}, recipients={len(users)}, channel={channel}"

@shared_task(name="api.tasks.test_notification_persistence")
def test_notification_persistence(user_id: int, msg: str = "persistence probe"):
    from django.contrib.auth import get_user_model
    U = get_user_model()
    u = U.objects.filter(id=user_id).first()
    if not u:
        return "no such user"
    n = notify_user(u, msg, notification_type="probe", data={"probe": "1"}, dry_run=True)
    return f"created notification id={n.id} for user={u.id}"

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
    Uses Shop.business_hours overrides; falls back to start_at/close_at.
    Supports multiple intervals per day (e.g., 09:00-14:00 and 15:00-18:00).
    """
    created_count = 0
    try:
        past_slots = Slot.objects.filter(end_time__lt=timezone.now(), bookings__isnull=True)
        past_slots.delete()

        today = timezone.localdate()
        target_end = today + timedelta(days=days_ahead - 1)

        for shop in Shop.objects.prefetch_related("services").all():
            services = shop.services.filter(is_active=True)

            for service in services:
                for offset in range((target_end - today).days + 1):
                    date = today + timedelta(days=offset)
                    weekday = date.strftime("%A").lower()

                    if (shop.close_days or []) and weekday in shop.close_days:
                        continue

                    # Get intervals for this date
                    intervals = shop.get_intervals_for_date(date)  # returns list[(time,time)]
                    if not intervals:
                        continue

                    duration = service.duration or 30

                    # Existing start times for that day
                    existing_times = set(
                        Slot.objects.filter(shop=shop, service=service, start_time__date=date)
                        .values_list("start_time", flat=True)
                    )

                    batch = []
                    for (start_t, end_t) in intervals:
                        start_dt = timezone.make_aware(datetime.combine(date, start_t))
                        end_dt   = timezone.make_aware(datetime.combine(date, end_t))
                        if end_dt <= start_dt:
                            continue

                        current = start_dt
                        while current + timedelta(minutes=duration) <= end_dt:
                            if current not in existing_times:
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

        logger.info(f"[Prefill Slots] Created {created_count} slots across all shops/services.")
        return f"Prefilled {days_ahead} days with {created_count} slots."
    except Exception as e:
        logger.error(f"[Prefill Slots] Error: {e}", exc_info=True)
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def send_upcoming_slot_reminders(self, window_minutes=30):
    """Send reminders via email, push, and save to DB for upcoming confirmed bookings."""
    now = timezone.now()
    window_end = now + timedelta(minutes=window_minutes)

    try:
        from payments.models import Booking

        # If your canonical “confirmed” state is 'confirmed' (matches SlotBooking usage),
        # use that. If payments.Booking uses a different value, update here.
        CONFIRMED = "confirmed"

        upcoming = (
            Booking.objects
            .select_related(
                "user", "shop", "slot", "slot__service"  # <-- FIX: pull service via slot
            )
            .filter(
                status=CONFIRMED,                  # <-- FIX: use the real confirmed state
                slot__start_time__gte=now,
                slot__start_time__lte=window_end,
            )
        )

        sent_count = 0

        for b in upcoming:
            user = b.user
            shop = b.shop
            service = b.slot.service  # <-- FIX: service comes from slot
            start_local = timezone.localtime(b.slot.start_time)

            subject = f"Reminder: {service.title} at {shop.name}"
            display_name = getattr(user, "name", None) or getattr(user, "email", "there")

            full_message = (
                f"Hi {display_name},\n\nJust a reminder that your booking for {service.title} "
                f"at {shop.name} is coming up soon!\n\n"
                f"Date & Time: {start_local.strftime('%A, %b %d at %I:%M %p')}\n\nSee you there!"
            )
            push_body = f"Your {service.title} booking at {shop.name} is at {start_local.strftime('%I:%M %p')}."

            push_data = {
                "type": "booking_reminder",
                "booking_id": str(b.id),
                "shop_id": str(shop.id),
                "service_id": str(service.id),
                "start_time": b.slot.start_time.isoformat(),
                # you can add a deeplink here, too
            }

            client_phone = getattr(user, 'phone_number', None)
            if client_phone:
                sms_body = f"Fidden Reminder: Your {service.title} booking at {shop.name} is at {start_local.strftime('%I:%M %p')} today."
                send_sms(client_phone, sms_body)
            else:
                 logger.warning(f"[Reminder] Cannot send SMS reminder to user {user.id}, no phone number.")

            # Email (optional)
            email = getattr(user, "email", None)
            if email:
                try:
                    send_mail(subject, full_message, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
                except Exception as e:
                    logger.warning(f"[Reminder] Failed to send email to {email}: {e}")

            # Persist in DB + send push
            try:
                notify_user(
                    user=user,
                    message=push_body,
                    notification_type="booking_reminder",
                    data={**push_data, "title": subject},
                    dry_run=False,  # ensure we actually send push
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"[Reminder] Failed for booking {b.id} user {user.id}: {e}", exc_info=True)

        logger.info(f"[Reminder] Processed {sent_count} reminders for upcoming slots.")
        return f"Processed {sent_count} reminders."

    except Exception as e:
        logger.error(f"[Reminder Task] Error: {e}", exc_info=True)
        raise self.retry(exc=e)



@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def cleanup_old_cancelled_bookings(self, days=7, batch_size=1000):
    """
    Cleanup old cancelled bookings, restore slot capacity.
    Locks a small batch with SELECT ... FOR UPDATE SKIP LOCKED inside a transaction.
    """
    cutoff = timezone.now() - timedelta(days=days)
    total_deleted = 0

    try:
        while True:
            # Lock a small batch atomically
            with transaction.atomic():
                batch = list(
                    SlotBooking.objects
                    .select_for_update(skip_locked=True)  # requires PostgreSQL
                    .select_related("slot")
                    .filter(status="cancelled", start_time__lt=cutoff)
                    .order_by("id")[:batch_size]
                )

                if not batch:
                    break

                # Count how many bookings we’re restoring per slot
                incr_by_slot = {}
                for b in batch:
                    incr_by_slot[b.slot_id] = incr_by_slot.get(b.slot_id, 0) + 1

                # Bulk bump capacity using F() so it’s atomic
                for slot_id, inc in incr_by_slot.items():
                    Slot.objects.filter(id=slot_id).update(
                        capacity_left=F("capacity_left") + inc
                    )

                # Bulk delete the batch
                SlotBooking.objects.filter(id__in=[b.id for b in batch]).delete()

                total_deleted += len(batch)

                # If we got less than a full batch, likely done
                if len(batch) < batch_size:
                    break

        msg = f"[Cleanup] Deleted {total_deleted} old cancelled bookings (older than {days} days)."
        logger.info(msg)
        return msg

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