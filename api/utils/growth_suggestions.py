from typing import List, Dict
from django.utils.timezone import now, timedelta
from django.db.models import Sum, Count, Avg, Q
import logging

from api.models import Revenue, Shop, Service, RatingReview, Slot, SlotBooking
from payments.models import Booking

logger = logging.getLogger(__name__)

# Thresholds
REPEAT_RATE_THRESHOLD = 30
CANCELLATION_RATE_THRESHOLD = 20
UTILIZATION_LOW_THRESHOLD = 40
UTILIZATION_HIGH_THRESHOLD = 80
REVENUE_GROWTH_THRESHOLD = 0
SERVICE_BOOKING_LOW_THRESHOLD = 3
SERVICE_RATING_LOW_THRESHOLD = 3.5
HIGH_RATING_THRESHOLD = 4.5

def generate_growth_suggestions(shop_id: int) -> List[Dict]:
    suggestions: Dict[str, Dict] = {}

    try:
        shop = Shop.objects.get(id=shop_id)

        if not shop.is_verified:
            return [{
                "suggestion_title": "Get Your Shop Verified",
                "short_description": "Verify your shop to unlock all growth features and attract more customers.",
                "category": "operational"
            }]

        today = now().date()
        last_week = today - timedelta(days=7)
        prev_week = today - timedelta(days=14)

        # -----------------------
        # Revenue calculation
        # -----------------------
        revenue_data = Revenue.objects.filter(shop_id=shop_id)
        current_revenue = revenue_data.filter(timestamp__gte=last_week).aggregate(total=Sum("revenue"))["total"] or 0
        prev_revenue = revenue_data.filter(timestamp__range=(prev_week, last_week)).aggregate(total=Sum("revenue"))["total"] or 0
        revenue_growth = ((current_revenue - prev_revenue) / prev_revenue * 100) if prev_revenue > 0 else 0

        # -----------------------
        # Booking & utilization
        # -----------------------
        bookings_qs = Booking.objects.filter(shop_id=shop_id)
        total_bookings = bookings_qs.count()
        cancelled_bookings = bookings_qs.filter(status="cancelled").count()
        completed_bookings = bookings_qs.filter(status="completed").count()
        cancellation_rate = (cancelled_bookings / total_bookings * 100) if total_bookings > 0 else 0
        utilization = (completed_bookings / total_bookings * 100) if total_bookings > 0 else 0

        repeat_users = bookings_qs.values("user").annotate(count=Count("id")).filter(count__gt=1).count()
        total_users = bookings_qs.values("user").distinct().count()
        repeat_rate = (repeat_users / total_users * 100) if total_users > 0 else 0

        # -----------------------
        # Service-based analysis
        # -----------------------
        low_booking_services = Service.objects.filter(
            shop_id=shop_id,
            slots__bookings__isnull=True
        ).distinct()

        low_rating_services = Service.objects.filter(
            shop_id=shop_id,
            ratings__rating__lt=SERVICE_RATING_LOW_THRESHOLD
        ).distinct()

        high_rating_services = Service.objects.filter(
            shop_id=shop_id,
            ratings__rating__gte=HIGH_RATING_THRESHOLD
        ).distinct()

        # -----------------------
        # Suggestion Engine
        # -----------------------

        # -------- Discount Suggestions --------
        if repeat_rate < REPEAT_RATE_THRESHOLD or low_booking_services.exists():
            suggestions["discount"] = {
                "suggestion_title": "Offer Discounts to Boost Bookings",
                "short_description": f"Some services have low bookings or repeat rate is low. Offer discounts or bundle promotions to attract new and returning customers.",
                "category": "discount"
            }
        elif revenue_growth < REVENUE_GROWTH_THRESHOLD:
            suggestions["discount"] = {
                "suggestion_title": "Revenue Decline Detected",
                "short_description": "Run a limited-time discount or loyalty campaign to increase revenue.",
                "category": "discount"
            }
        elif utilization < UTILIZATION_LOW_THRESHOLD:
            suggestions["discount"] = {
                "suggestion_title": "Improve Off-Peak Utilization",
                "short_description": "Offer discounts for under-booked time slots to increase shop utilization.",
                "category": "discount"
            }

        # -------- Operational Suggestions --------
        if cancellation_rate > CANCELLATION_RATE_THRESHOLD or low_rating_services.exists():
            suggestions["operational"] = {
                "suggestion_title": "Enhance Customer Experience",
                "short_description": "High cancellations or low ratings detected. Review service quality, training, and booking policies to improve satisfaction.",
                "category": "operational"
            }
        elif utilization > UTILIZATION_HIGH_THRESHOLD:
            suggestions["operational"] = {
                "suggestion_title": "Maximize Popular Slots",
                "short_description": "Some slots are fully booked. Consider increasing capacity, extending hours, or optimizing staffing.",
                "category": "operational"
            }
        elif high_rating_services.exists() and repeat_rate < 50:
            suggestions["operational"] = {
                "suggestion_title": "Upsell High-Rated Services",
                "short_description": "Some services have high ratings but low repeat bookings. Promote them to increase repeat business.",
                "category": "operational"
            }

        # -------- Marketing Suggestions --------
        if revenue_growth <= REVENUE_GROWTH_THRESHOLD and repeat_rate < REPEAT_RATE_THRESHOLD:
            suggestions["marketing"] = {
                "suggestion_title": "Run Targeted Marketing Campaign",
                "short_description": "Revenue growth is flat and repeat bookings are low. Launch email, social media, or ad campaigns with promotions.",
                "category": "marketing"
            }
        elif utilization < UTILIZATION_LOW_THRESHOLD:
            suggestions["marketing"] = {
                "suggestion_title": "Promote Off-Peak Hours",
                "short_description": "Under-booked slots detected. Run marketing campaigns offering discounts to increase bookings during off-peak hours.",
                "category": "marketing"
            }
        elif total_bookings > 0 and repeat_rate > 50:
            suggestions["marketing"] = {
                "suggestion_title": "Leverage Happy Customers",
                "short_description": "High repeat rate detected. Encourage referrals, reviews, or social media sharing to attract new customers.",
                "category": "marketing"
            }

    except Shop.DoesNotExist:
        logger.warning(f"Shop {shop_id} does not exist.")
    except Exception as e:
        logger.exception(f"Error generating growth suggestions for shop {shop_id}: {e}")

    # Return suggestions as a list (1 per category)
    return list(suggestions.values())
