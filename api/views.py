# api/views.py
import random
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.db.models import Avg, Sum
from django.core.cache import cache
from django.core.mail import send_mail
from django.utils.timezone import make_aware
from django.core.mail import EmailMultiAlternatives, get_connection
from .models import (
    AutoFillLog,
    PerformanceAnalytics,
    Shop, 
    Service, 
    RatingReview, 
    ServiceCategory, 
    Slot, 
    SlotBooking, 
    FavoriteShop,
    Promotion,
    ServiceWishlist,
    Reply,
    ChatThread, 
    Message, 
    Device,
    Notification,
    Revenue,
    Coupon,
    WeeklySummary
)
from payments.models import Booking
from .serializers import (
    AIReportSerializer,
    ShopSerializer, 
    ServiceSerializer, 
    RatingReviewSerializer, 
    ServiceCategorySerializer, 
    SlotBookingSerializer,
    ShopListSerializer, 
    ShopDetailSerializer, 
    ServiceListSerializer,
    ServiceDetailSerializer,
    FavoriteShopSerializer,
    PromotionSerializer,
    ServiceWishlistSerializer,
    ReplyCreateSerializer,
    ShopRatingReviewSerializer, 
    ChatThreadSerializer, 
    MessageSerializer, 
    DeviceSerializer,
    NotificationSerializer,
    RevenueSerializer,
    SuggestionSerializer,
    CouponSerializer,
    UserCouponRetrieveSerializer,
    WeeklySummaryActionSerializer,
    WeeklySummarySerializer,
)
from .permissions import IsOwnerAndOwnerRole, IsOwnerRole
from datetime import date, datetime, timedelta
from django.utils import timezone
from django.db.models import Avg, Count, Q, Value, FloatField, OuterRef, Subquery
from django.db.models.functions import Coalesce
from .pagination import ServicesCursorPagination, ReviewCursorPagination, MessageCursorPagination
from urllib.parse import urlencode
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from collections import OrderedDict
from django.core.paginator import Paginator
from api.utils.helper_function import haversine, get_relevance
from django.db.models import Prefetch
from rest_framework.pagination import PageNumberPagination
from api.utils.fcm import notify_user
from api.utils.growth_suggestions import generate_growth_suggestions
from .tasks import auto_cancel_booking
import logging
from .serializers import PerformanceAnalyticsSerializer, AIAutoFillSettingsSerializer
from .models import AIAutoFillSettings
from django.db.models import IntegerField, Case, When, Value, F


logger = logging.getLogger(__name__)


class AIAutoFillSettingsView(APIView):
    permission_classes = [IsAuthenticated, IsOwnerRole]

    def get(self, request):
        settings, _ = AIAutoFillSettings.objects.get_or_create(shop=request.user.shop)
        serializer = AIAutoFillSettingsSerializer(settings) # Create this serializer
        return Response(serializer.data)

    def patch(self, request):
        settings, _ = AIAutoFillSettings.objects.get_or_create(shop=request.user.shop)
        serializer = AIAutoFillSettingsSerializer(settings, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class HoldSlotAndBookView(APIView):
    """
    Allows a user to claim an auto-fill offer.
    It creates a temporary, exclusive hold on the slot for a few minutes
    to allow the user to complete the booking process.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, slot_id):
        user = request.user
        
        try:
            # Use select_for_update to lock the slot row during the transaction
            with transaction.atomic():
                slot = Slot.objects.select_for_update().get(id=slot_id)

                # 1. Check if the slot is still available
                if slot.capacity_left <= 0:
                    return Response(
                        {"error": "This slot was just booked by someone else."},
                        status=status.HTTP_409_CONFLICT  # 409 Conflict
                    )

                # 2. Check for an existing hold on the slot
                hold_key = f"slot_hold_{slot_id}"
                if cache.get(hold_key):
                    return Response(
                        {"error": "This slot is currently on hold. Please try again in a few moments."},
                        status=status.HTTP_409_CONFLICT
                    )

                # 3. Create a 5-minute hold for the current user
                cache.set(hold_key, user.id, timeout=300)  # 300 seconds = 5 minutes
                logger.info(f"Slot {slot_id} is now on hold for user {user.id}.")

                # 4. Create the preliminary booking record in 'pending' state
                # This uses the Booking model from your payments app
                new_booking = Booking.objects.create(
                    user=user,
                    shop=slot.shop,
                    service=slot.service,
                    slot=slot, # Link to the actual Slot
                    status='pending', # Start as pending until payment is confirmed
                    start_time=slot.start_time,
                    end_time=slot.end_time,
                )
                
                # 5. Decrement slot capacity immediately
                slot.capacity_left -= 1
                slot.save(update_fields=['capacity_left'])

        except Slot.DoesNotExist:
            return Response({"error": "Slot not found."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error in HoldSlotAndBookView: {e}", exc_info=True)
            return Response({"error": "An unexpected error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # The user's app should now proceed to the payment screen.
        # The CreatePaymentIntentView will be called next by the app.
        return Response({
            "success": True,
            "message": "Slot is now on hold. Please complete your payment within 5 minutes.",
            "booking_id": new_booking.id,
            "slot_id": slot_id,
        }, status=status.HTTP_200_OK)

class ShopListCreateView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]

    def get(self, request):
        user = request.user
        if getattr(user, 'role', None) != 'owner':
            return Response({"detail": "You do not have a shop."}, status=status.HTTP_403_FORBIDDEN)

        shop = getattr(user, "shop", None)
        if not shop:
            return Response({"detail": "No shop found for this user."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ShopSerializer(shop, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        if getattr(request.user, 'role', None) != 'owner':
            return Response({"detail": "Only owners can create shops."}, status=status.HTTP_403_FORBIDDEN)

        if hasattr(request.user, 'shop'):
            return Response({"detail": "You already have a shop."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = ShopSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            shop = serializer.save(owner=request.user)
            return Response(
                ShopSerializer(shop, context={'request': request}).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ShopRetrieveUpdateDestroyView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]

    def get_object(self, pk):
        return get_object_or_404(Shop, pk=pk, owner=self.request.user)

    def get(self, request, pk):
        shop = self.get_object(pk)
        serializer = ShopSerializer(shop, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk):
        shop = self.get_object(pk)
        serializer = ShopSerializer(shop, data=request.data, context={'request': request})
        if serializer.is_valid():
            shop = serializer.save()
            return Response(ShopSerializer(shop, context={'request': request}).data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        shop = self.get_object(pk)
        serializer = ShopSerializer(shop, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            shop = serializer.save()
            return Response(ShopSerializer(shop, context={'request': request}).data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        shop = self.get_object(pk)
        shop.delete()
        return Response({"success": True, "message": "Shop deleted successfully."}, status=status.HTTP_200_OK)

class ServiceCategoryListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        categories = ServiceCategory.objects.all()
        serializer = ServiceCategorySerializer(
            categories, 
            many=True, 
            context={'request': request}  # pass request here
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

class ServiceListCreateView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsOwnerRole]

    def get(self, request):
        shop = Shop.objects.filter(owner=request.user).first()
        if not shop:
            return Response({"detail": "You must create a shop before accessing services."}, status=status.HTTP_400_BAD_REQUEST)

        services = shop.services.all()
        serializer = ServiceSerializer(services, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        shop = Shop.objects.filter(owner=request.user).first()
        if not shop:
            return Response({"detail": "You must create a shop before adding services."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = ServiceSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            service = serializer.save(shop=shop)
            return Response(ServiceSerializer(service, context={'request': request}).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ServiceRetrieveUpdateDestroyView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsOwnerRole]

    def get_object(self, request, pk):
        shop = Shop.objects.filter(owner=request.user).first()
        if not shop:
            return None
        return get_object_or_404(Service, pk=pk, shop=shop)

    def get(self, request, pk):
        service = self.get_object(request, pk)
        if not service:
            return Response({"detail": "You must create a shop before accessing services."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = ServiceSerializer(service, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk):
        service = self.get_object(request, pk)
        if not service:
            return Response({"detail": "You must create a shop before updating services."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = ServiceSerializer(service, data=request.data, context={'request': request})
        if serializer.is_valid():
            service = serializer.save()
            return Response(ServiceSerializer(service, context={'request': request}).data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        service = self.get_object(request, pk)
        if not service:
            return Response({"detail": "You must create a shop before updating services."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = ServiceSerializer(service, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            service = serializer.save()
            return Response(ServiceSerializer(service, context={'request': request}).data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        service = self.get_object(request, pk)
        if not service:
            return Response({"detail": "You must create a shop before deleting services."}, status=status.HTTP_400_BAD_REQUEST)

        service.delete()
        return Response({"success": True, "message": "Service deleted successfully."}, status=status.HTTP_200_OK)

class UserRatingReviewView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if getattr(user, 'role', None) != 'user':
            return Response({"detail": "Only users can view reviews."}, status=status.HTTP_403_FORBIDDEN)

        shop_id = request.query_params.get('shop')
        service_id = request.query_params.get('service')

        reviews = RatingReview.objects.filter(user__role='user')

        if shop_id:
            reviews = reviews.filter(shop_id=shop_id)
        if service_id:
            reviews = reviews.filter(service_id=service_id)

        avg_rating = reviews.aggregate(avg=Avg('rating'))['avg'] or 0
        total_reviews = reviews.count()

        serializer = RatingReviewSerializer(reviews, many=True, context={'request': request})
        return Response({
            "average_rating": round(avg_rating, 2),
            "total_reviews": total_reviews,
            "reviews": serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request):
        user = request.user
        if getattr(user, 'role', None) != 'user':
            return Response({"detail": "Only users can create reviews."}, status=status.HTTP_403_FORBIDDEN)

        serializer = RatingReviewSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            review = serializer.save()
            return Response(RatingReviewSerializer(review, context={'request': request}).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class SlotListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, shop_id):
        service_id = request.query_params.get('service')
        date_str = request.query_params.get('date')
        if not service_id or not date_str:
            return Response({"detail": "Query params 'service' and 'date' required."}, status=400)

        try:
            date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return Response({"detail": "Invalid date format."}, status=400)

        start_of_day = timezone.make_aware(datetime.combine(date, datetime.min.time()))
        end_of_day = timezone.make_aware(datetime.combine(date, datetime.max.time()))

        slots = Slot.objects.select_related('shop', 'service').filter(
            shop_id=shop_id, service_id=service_id,
            start_time__gte=start_of_day,
            start_time__lte=end_of_day
        ).order_by('start_time')

        results = []
        for s in slots:
            service_ok = s.capacity_left > 0
            overlap_count = SlotBooking.objects.filter(
                shop=s.shop,
                status='confirmed',
                start_time__lt=s.end_time,
                end_time__gt=s.start_time
            ).count()
            shop_ok = overlap_count < s.shop.capacity
            results.append({
                "id": s.id,
                "shop": s.shop_id,
                "service": s.service_id,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "capacity_left": s.capacity_left,
                "available": service_ok and shop_ok
            })
        return Response({"slots": results}, status=200)

class SlotBookingView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SlotBookingSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        booking = serializer.save()

        # Schedule auto-cancel task after 5 minutes (best-effort)
        try:
            auto_cancel_booking.apply_async((booking.id,), countdown=5 * 60)
        except Exception as exc:
            logger.exception("Failed to enqueue auto_cancel_booking for booking_id=%s: %s", booking.id, exc)

        return Response(SlotBookingSerializer(booking).data, status=status.HTTP_201_CREATED)

class CancelSlotBookingView(APIView):
    def post(self, request, booking_id):  # <- match URL param
        # Get the booking for the logged-in user
        booking = get_object_or_404(SlotBooking, id=booking_id, user=request.user)

        if booking.status == "cancelled":
            return Response(
                {"error": "This booking is already cancelled."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Mark booking as cancelled
        booking.status = "cancelled"
        booking.save(update_fields=["status"])

        # Restore capacity for the slot
        slot = booking.slot
        slot.capacity_left += 1
        slot.save(update_fields=["capacity_left"])

        # Restore capacity for the shop
        shop = slot.shop
        shop.capacity += 1
        shop.save(update_fields=["capacity"])

        return Response(
            {
                "message": "Booking cancelled successfully.",
                "booking_id": booking.id,
                "status": booking.status
            },
            status=status.HTTP_200_OK
        )

class AllShopsListView(APIView):
    """
    Fetch all shops with id, name, address, avg_rating, review_count, location, distance, shop_img, badge.
    Sort priority:
        1. Nearest to provided location (optional, lat/lon in request.data["location"])
        2. Higher avg_rating
        3. Higher review_count
    Supports search (?search=...) and manual cursor pagination.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if getattr(user, 'role', None) != 'user':
            return Response({"detail": "Only users can view shops."}, status=status.HTTP_403_FORBIDDEN)

        search_query = request.query_params.get('search', '')
        user_location = request.data.get("location")  # optional
        page_size = request.query_params.get('top', 10)
        cursor = request.query_params.get('cursor', 0)

        try:
            page_size = int(page_size)
        except ValueError:
            page_size = 10

        try:
            cursor = int(cursor)
        except ValueError:
            cursor = 0

        # Pull subscription+plan in one go to avoid N+1 when serializer asks for is_priority
        shops_qs = (
            Shop.objects
            .filter(is_verified=True)
            .select_related("subscription__plan")
        )
        if search_query:
            shops_qs = shops_qs.filter(
                Q(name__iregex=search_query) | Q(address__iregex=search_query)
            )

        shops_qs = shops_qs.annotate(
        avg_rating=Coalesce(Avg('ratings__rating'), Value(0.0, output_field=FloatField())),
        review_count=Count(
            'ratings',
            filter=Q(ratings__review__isnull=False) & ~Q(ratings__review__exact='')
        ),
        #  compute a plan-based priority boost (Icon > Momentum; only if plan is priority)
        plan_priority=Case(
            When(subscription__plan__priority_marketplace_ranking=True, then=Value(1)),
            default=Value(0), output_field=IntegerField()
        ),
        tier_weight=Case(
            When(subscription__plan__name="Icon", then=Value(2)),
            When(subscription__plan__name="Momentum", then=Value(1)),
            default=Value(0), output_field=IntegerField()
        ),
        boost_score=F('plan_priority') * Value(10) + F('tier_weight') * Value(5),
    )

        # order by boost first, then rating/reviews as you already do
        shops_qs = shops_qs.order_by(
            F('boost_score').desc(nulls_last=True),
            F('avg_rating').desc(nulls_last=True),
            F('review_count').desc(nulls_last=True),
        )

        # Serialize with distance and badge
        serializer = ShopListSerializer(
            shops_qs, many=True, context={"request": request, "user_location": user_location}
        )
        shops_list = serializer.data

        # Sort by distance -> ranking_power -> avg_rating -> review_count
        # replace your final Python sort with this
        shops_list = sorted(
            shops_list,
            key=lambda x: (
                x["distance"] if x["distance"] is not None else float("inf"),
                -x.get("boost_score", 0),   # Icon > Momentum > others
                -x["avg_rating"],
                -x["review_count"],
            )
        )



        # Manual cursor pagination
        start = cursor
        end = cursor + page_size
        results = shops_list[start:end]

        next_cursor = end if end < len(shops_list) else None
        prev_cursor = max(0, start - page_size) if start > 0 else None

        base_url = request.build_absolute_uri().split('?')[0]

        return Response(OrderedDict([
            ("next", f"{base_url}?{urlencode({'cursor': next_cursor, 'top': page_size})}" if next_cursor is not None else None),
            ("previous", f"{base_url}?{urlencode({'cursor': prev_cursor, 'top': page_size})}" if prev_cursor is not None else None),
            ("results", results)
        ]), status=status.HTTP_200_OK)

class ShopDetailView(APIView):
    """
    Fetch detailed information for a single shop:
        - shop name, address, location, avg_rating, review_count,
        - about_us, start_at, close_at, shop_img, close_days,
        - services (active only), reviews (for this shop only)
    No distance calculation.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, shop_id):
        user = request.user
        if getattr(user, 'role', None) != 'user':
            return Response({"detail": "Only users can view shops."}, status=status.HTTP_403_FORBIDDEN)
        try:
            shop = Shop.objects.annotate(
                avg_rating=Coalesce(
                    Avg('ratings__rating'),
                    0.0
                ),
                review_count=Count(
                    'ratings',
                    filter=Q(ratings__review__isnull=False) & ~Q(ratings__review__exact='')
                )
            ).get(id=shop_id)
        except Shop.DoesNotExist:
            return Response({"detail": "Shop not found."}, status=status.HTTP_404_NOT_FOUND)

        # Get category_id from query params and pass to serializer
        category_id = request.query_params.get('category_id')
        serializer = ShopDetailSerializer(shop, context={'request': request,  'category_id': category_id})
        return Response(serializer.data, status=status.HTTP_200_OK)

class AllServicesListView(APIView):
    """
    Fetch all active services with:
        - title, price, discount_price
        - shop_id, shop_address
        - avg_rating, review_count
        - service_img
    Supports optional search (?search=...).
    Sorted by:
        1. avg_rating (desc)
        2. review_count (desc)
    Supports cursor-based pagination with optional 'top' param for page size.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if getattr(user, "role", None) != "user":
            return Response({"detail": "Only users can view services."}, status=status.HTTP_403_FORBIDDEN)

        search_query = request.query_params.get("search", "")
        category_id = request.query_params.get("category")
        shop_id = request.query_params.get("shop")
        min_price = request.query_params.get("min_price")
        max_price = request.query_params.get("max_price")
        max_duration = request.query_params.get("max_duration")
        min_rating = request.query_params.get("min_rating")
        max_distance = request.query_params.get("max_distance")  # still query param for filtering
        user_location = request.data.get("location")  # user location from body, format "lon,lat"

        services_qs = (
            Service.objects.filter(
                is_active=True,
                shop__is_verified=True
            )
            .select_related("shop")
            .annotate(
                avg_rating=Coalesce(Avg("ratings__rating"), Value(0.0, output_field=FloatField())),
                review_count=Count(
                    "ratings",
                    filter=Q(ratings__review__isnull=False) & ~Q(ratings__review__exact=""),
                ),
            )
        )

        if category_id:  # <-- Add this block
            services_qs = services_qs.filter(category_id=category_id)

        if shop_id:  # <-- Add this block
            services_qs = services_qs.filter(shop_id=shop_id)

        # Price filter
        if min_price:
            services_qs = services_qs.filter(discount_price__gte=min_price)
        if max_price:
            services_qs = services_qs.filter(discount_price__lte=max_price)

        # Duration filter
        if max_duration:
            services_qs = services_qs.filter(duration__lte=max_duration)

        # Minimum rating filter
        if min_rating:
            services_qs = services_qs.filter(avg_rating__gte=float(min_rating))

        if search_query:
            services_qs = services_qs.filter(
                Q(title__iregex=search_query) | Q(shop__name__iregex=search_query)
            )

        # Convert to list if distance filtering is needed
        services_list = list(services_qs)
        if user_location and max_distance:
            max_distance = float(max_distance)

            def calculate_distance(service):
                try:
                    # Parse "lon,lat" format
                    user_lon, user_lat = map(float, user_location.split(","))
                    shop_lon, shop_lat = map(float, service.shop.location.split(","))

                    # Use haversine (expects lat, lon order)
                    return haversine(user_lat, user_lon, shop_lat, shop_lon) * 1000  # meters
                except Exception:
                    return float("inf")

            services_list = [
                s for s in services_list if calculate_distance(s) <= max_distance
            ]

        # Cursor pagination will handle ordering and page size
        paginator = ServicesCursorPagination()
        page = paginator.paginate_queryset(services_qs, request)

        serializer = ServiceListSerializer(
            page, many=True, context={"request": request, "user_location": request.data.get("location")}
        )
        return paginator.get_paginated_response(serializer.data)

class ServiceDetailView(APIView):
    """
    Get details of a specific service:
        - service_img, title, price, discount_price
        - description, duration
        - shop_id, shop_name
        - avg_rating, review_count
        - reviews (id, shop, user, user_name, user_img, rating, review)
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, service_id):
        user = request.user
        if getattr(user, "role", None) != "user":
            return Response({"detail": "Only users can view services."}, status=status.HTTP_403_FORBIDDEN)

        service = (
            Service.objects.filter(id=service_id, is_active=True)
            .select_related("shop")
            .annotate(
                avg_rating=Coalesce(Avg("ratings__rating"), Value(0.0, output_field=FloatField())),
                review_count=Count(
                    "ratings",
                    filter=Q(ratings__review__isnull=False) & ~Q(ratings__review__exact=""),
                ),
            )
            .first()
        )

        if not service:
            return Response({"detail": "Service not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ServiceDetailSerializer(service, context={"request": request})

        # Return serializer data directly, no extra "service" key
        return Response(serializer.data, status=status.HTTP_200_OK)

class FavoriteShopView(APIView):
    """
    POST: Add a shop to favorites (shop_id in body)
    GET: List all favorite shops of the logged-in user with full shop details
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if getattr(user, "role", None) != "user":
            return Response({"detail": "Only users can view services."}, status=status.HTTP_403_FORBIDDEN)

        serializer = FavoriteShopSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        favorite = serializer.save()
        return Response({
            "id": favorite.id,
            "user_id": favorite.user.id,
            "shop_id": favorite.shop.id,
            "created_at": favorite.created_at
        }, status=status.HTTP_201_CREATED)

    def get(self, request):
        user = request.user
        if getattr(user, "role", None) != "user":
            return Response({"detail": "Only users can view services."}, status=status.HTTP_403_FORBIDDEN)

        user_location = request.data.get("location")  # optional: "lon,lat"
        favorites = FavoriteShop.objects.filter(user=request.user, shop__is_verified=True).select_related('shop')
        serializer = FavoriteShopSerializer(favorites, many=True, context={'request': request, 'user_location': user_location})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request):
        user = request.user
        if getattr(user, "role", None) != "user":
            return Response({"detail": "Only users can view services."}, status=status.HTTP_403_FORBIDDEN)

        favorite_id = request.data.get("id")
        if not favorite_id:
            return Response({"detail": "ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            favorite = FavoriteShop.objects.get(id=favorite_id, user=request.user)
            favorite.delete()
            return Response({"detail": "Favorite shop deleted successfully."}, status=status.HTTP_204_NO_CONTENT)
        except FavoriteShop.DoesNotExist:
            return Response({"detail": "Favorite shop not found."}, status=status.HTTP_404_NOT_FOUND)

class PromotionListView(APIView):
    """
    GET: Retrieve all active promotions
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        promotions = Promotion.objects.filter(is_active=True).order_by('-created_at')
        serializer = PromotionSerializer(promotions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class ServiceWishlistView(APIView):
    """
    POST: Add a service to wishlist (service_id in body)
    GET: List all wishlisted services for logged-in user (only active shops)
    DELETE: Remove a service from wishlist (service_id in body)
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if getattr(user, "role", None) != "user":
            return Response({"detail": "Only users can view services."}, status=status.HTTP_403_FORBIDDEN)

        serializer = ServiceWishlistSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        wishlist = serializer.save()
        return Response({
            "id": wishlist.id,
            "user_id": wishlist.user.id,
            "service_id": wishlist.service.id,
            "created_at": wishlist.created_at
        }, status=status.HTTP_201_CREATED)

    def get(self, request):
        user = request.user
        if getattr(user, "role", None) != "user":
            return Response({"detail": "Only users can view services."}, status=status.HTTP_403_FORBIDDEN)

        wishlists = ServiceWishlist.objects.filter(
            user=request.user,
            service__is_active=True,
            service__shop__is_verified=True
        ).select_related('service__shop', 'service__category')

        serializer = ServiceWishlistSerializer(wishlists, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request):
        user = request.user
        if getattr(user, "role", None) != "user":
            return Response({"detail": "Only users can view services."}, status=status.HTTP_403_FORBIDDEN)

        wishList_id = request.data.get("id")
        wishlist_item = ServiceWishlist.objects.get(user=request.user, id=wishList_id)

        if not wishlist_item:
            return Response({"detail": "Service not found in wishlist"}, status=status.HTTP_404_NOT_FOUND)

        wishlist_item.delete()
        return Response({"detail": "Service removed from wishlist"}, status=status.HTTP_204_NO_CONTENT)

class GlobalSearchView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # --- Query param from URL ---
        query = request.query_params.get("q", "").strip()
        if not query:
            return Response({"detail": "Query parameter 'q' is required."}, status=400)

        # --- Location from POST body ---
        location = request.data.get("location")  # expects "lon,lat"
        page_size = request.data.get("page_size", 10)
        try:
            page_size = int(page_size)
        except ValueError:
            page_size = 10

        lat, lon = None, None
        if location:
            try:
                lon, lat = map(float, location.split(","))
            except ValueError:
                pass

        query_words = query.lower().split()
        results = []

        # --- Shops search ---
        shops = Shop.objects.annotate(
            avg_rating=Avg("ratings__rating"),
            review_count=Count("ratings")
        ).distinct()

        for shop in shops:
            shop_text = f"{shop.name} {shop.address}".lower()
            shop_match = all(word in shop_text for word in query_words)

            # Check services of shop
            service_match = False
            for service in shop.services.all():
                title_text = service.title.lower() if service.title else ""
                category_text = service.category.name.lower() if service.category else ""
                if all(word in title_text or word in category_text for word in query_words):
                    service_match = True
                    break

            if not (shop_match or service_match):
                continue

            # Calculate distance if location provided
            distance = None
            if lat is not None and lon is not None and shop.location:
                try:
                    shop_lon, shop_lat = map(float, shop.location.split(","))
                    distance = haversine(lat, lon, shop_lat, shop_lon)
                except ValueError:
                    pass

            relevance = max(
                get_relevance(shop.name, query) or 0,
                get_relevance(shop.address or "", query) or 0
            ) or 0.5

            results.append({
                "type": "shop",
                "id": shop.id,
                "title": shop.name,
                "extra_info": shop.address,
                "image": request.build_absolute_uri(shop.shop_img.url) if shop.shop_img else None,
                "distance": distance,
                "rating": shop.avg_rating or 0,
                "reviews": shop.review_count or 0,
                "relevance": relevance,
            })

        # --- Services search ---
        services = Service.objects.annotate(
            avg_rating=Avg("ratings__rating"),
            review_count=Count("ratings")
        ).select_related("shop", "category").distinct()

        for service in services:
            if not service.shop:
                continue

            title_text = service.title.lower() if service.title else ""
            category_text = service.category.name.lower() if service.category else ""
            if not all(word in title_text or word in category_text for word in query_words):
                continue

            distance = None
            if lat is not None and lon is not None and service.shop.location:
                try:
                    shop_lon, shop_lat = map(float, service.shop.location.split(","))
                    distance = haversine(lat, lon, shop_lat, shop_lon)
                except ValueError:
                    pass

            relevance = max(
                get_relevance(service.title, query) or 0,
                get_relevance(category_text, query) or 0
            ) or 0.5

            results.append({
                "type": "service",
                "id": service.id,
                "title": service.title,
                "extra_info": f"{service.shop.name} · ${service.price}",
                "image": request.build_absolute_uri(service.service_img.url) if service.service_img else None,
                "distance": distance,
                "rating": service.avg_rating or 0,
                "reviews": service.review_count or 0,
                "relevance": relevance,
            })

        # --- Sort results: distance → relevance → rating → review count ---
        results.sort(key=lambda x: (
            x["distance"] if x["distance"] is not None else float("inf"),
            -x["relevance"],
            -x["rating"],
            -x["reviews"]
        ))

        # --- Pagination ---
        paginator = PageNumberPagination()
        paginator.page_size = page_size
        paginated_results = paginator.paginate_queryset(results, request)
        return paginator.get_paginated_response(paginated_results)

class ReplyCreateView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, rating_review_id):
        user = request.user
        if getattr(user, 'role', None) != 'owner':
            return Response({"detail": "You do not have a shop."}, status=status.HTTP_403_FORBIDDEN)

        try:
            # Get the rating review instance
            rating_review = RatingReview.objects.get(id=rating_review_id)
        except RatingReview.DoesNotExist:
            return Response(
                {"error": "Rating review not found", "status": status.HTTP_404_NOT_FOUND},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = ReplyCreateSerializer(
            data=request.data, 
            context={
                'request': request,
                'rating_review': rating_review
            }
        )
        serializer.is_valid(raise_exception=True)
        reply = serializer.save()
        
        return Response(
            {
                "message": "Reply created successfully",
                "id": reply.id,
                "status": status.HTTP_201_CREATED
            },
            status=status.HTTP_201_CREATED
        )

class ShopRatingReviewsView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]
    pagination_class = ReviewCursorPagination

    def get(self, request, shop_id):
        user = request.user

        # Check if user is an owner
        if getattr(user, "role", None) != "owner":
            return Response(
                {"detail": "Only owners can access this resource."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Verify that the shop belongs to the owner
        try:
            shop = Shop.objects.get(id=shop_id, owner=user)
        except Shop.DoesNotExist:
            return Response(
                {"detail": "Shop not found or you don't have permission to access it."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Prefetch replies for better performance
        replies_prefetch = Prefetch(
            "replies",
            queryset=Reply.objects.select_related("user").order_by("created_at"),
        )

        # Base queryset
        queryset = (
            RatingReview.objects.filter(shop=shop)
            .select_related("service", "user")
            .prefetch_related(replies_prefetch)
            .order_by("-created_at")
        )

        # Search filter
        search = request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(service__title__icontains=search)  # service_name
                | Q(user__name__icontains=search)    # user_name
                | Q(review__icontains=search)        # review text
            )

        # Apply cursor pagination
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)

        serializer = ShopRatingReviewSerializer(
            page,
            many=True,
            context={"request": request},
        )

        return paginator.get_paginated_response({
            "shop_id": shop.id,
            "shop_name": shop.name,
            "count": queryset.count(),
            "reviews": serializer.data,
        })

class RegisterDeviceView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = DeviceSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        device = serializer.save()

        return Response({
            "success": True,
            "device": serializer.data
        })

class UserMessageView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, shop_id):
        user = request.user
        content = request.data.get("content")
        shop = Shop.objects.get(id=shop_id)
        thread, _ = ChatThread.objects.get_or_create(shop=shop, user=user)
        message = Message.objects.create(thread=thread, sender=user, content=content)

        # Notify owner and get the created notification
        from api.models import Notification
        notification = Notification.objects.create(
            recipient=shop.owner,
            message=f"New message from {user.email}",
            notification_type="chat",
            data={"thread_id": thread.id}
        )
        notify_user(shop.owner, f"New message from {user.email}", data={"thread_id": thread.id})

        # Broadcast notification over websockets to recipient
        channel_layer = get_channel_layer()
        notification_data = {
            "id": notification.id,
            "message": notification.message,
            "notification_type": notification.notification_type,
            "data": notification.data,
            "is_read": notification.is_read,
            "created_at": notification.created_at.isoformat()
        }
        async_to_sync(channel_layer.group_send)(
            f"user_{shop.owner.id}",
            {"type": "notification", "notification": notification_data},
        )

        # Broadcast over websockets to recipient and echo to sender
        message_data = MessageSerializer(message).data
        async_to_sync(channel_layer.group_send)(
            f"user_{shop.owner.id}",
            {"type": "chat_message", "message": message_data},
        )
        async_to_sync(channel_layer.group_send)(
            f"user_{user.id}",
            {"type": "chat_message", "message": message_data},
        )

        return Response(message_data)

class OwnerMessageView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, thread_id):
        owner = request.user
        content = request.data.get("content")
        thread = ChatThread.objects.get(id=thread_id)

        if thread.shop.owner != owner:
            return Response({"error": "Not authorized"}, status=403)

        message = Message.objects.create(thread=thread, sender=owner, content=content)
        # Notify user and get the created notification
        from api.models import Notification
        notification = Notification.objects.create(
            recipient=thread.user,
            message=f"Reply from {owner.email}",
            notification_type="chat",
            data={"thread_id": thread.id}
        )
        notify_user(thread.user, f"Reply from {owner.email}", data={"thread_id": thread.id})

        # Broadcast notification over websockets to recipient
        channel_layer = get_channel_layer()
        notification_data = {
            "id": notification.id,
            "message": notification.message,
            "notification_type": notification.notification_type,
            "data": notification.data,
            "is_read": notification.is_read,
            "created_at": notification.created_at.isoformat()
        }
        async_to_sync(channel_layer.group_send)(
            f"user_{thread.user.id}",
            {"type": "notification", "notification": notification_data},
        )

        # Broadcast over websockets to recipient and echo to sender
        message_data = MessageSerializer(message).data
        async_to_sync(channel_layer.group_send)(
            f"user_{thread.user.id}",
            {"type": "chat_message", "message": message_data},
        )
        async_to_sync(channel_layer.group_send)(
            f"user_{owner.id}",
            {"type": "chat_message", "message": message_data},
        )

        return Response(message_data)

class ThreadListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # Filter threads belonging to the user or as shop owner
        threads = ChatThread.objects.filter(
            Q(user=user) | Q(shop__owner=user)
        ).order_by("-created_at")

        # Annotate last message
        last_message_subquery = Message.objects.filter(
            thread=OuterRef('pk')
        ).order_by('-timestamp')

        threads = threads.annotate(
            last_message_id=Subquery(last_message_subquery.values('id')[:1])
        )

        serializer = ChatThreadSerializer(
            threads,
            many=True,
            context={'request': request, 'last_message_only': True}
        )
        return Response(serializer.data)

class ThreadDetailsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, thread_id):
        user = request.user

        # Get thread and check permissions
        thread = ChatThread.objects.filter(
            id=thread_id
        ).filter(
            Q(user=user) | Q(shop__owner=user)
        ).first()

        if not thread:
            return Response({"detail": "Thread not found or access denied."}, status=404)

        queryset = Message.objects.filter(thread=thread).order_by('-timestamp')

        # Apply cursor pagination manually
        paginator = MessageCursorPagination()
        page = paginator.paginate_queryset(queryset, request)

        serializer = MessageSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)

class NotificationsView(APIView):
    """
    List all notifications for the authenticated user.
    Option: Mark all as read when listing.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Only fetch notifications for the logged-in user
        notifications = Notification.objects.filter(recipient=request.user).order_by("-created_at")

        # # Mark all as read
        # notifications.update(is_read=True)

        serializer = NotificationSerializer(notifications, many=True)
        return Response(serializer.data)

class NotificationDetailView(APIView):
    """
    Retrieve a single notification.
    Marks as read when viewed.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            notification = Notification.objects.get(pk=pk, recipient=request.user)
        except Notification.DoesNotExist:
            return Response({"detail": "Notification not found."}, status=404)

        # Mark as read if not already
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=["is_read"])

        serializer = NotificationSerializer(notification)
        return Response(serializer.data)

class WeeklyShopRevenueView(APIView):

    permission_classes = [IsAuthenticated]
    """
    Get all revenue records for a given shop_id with shop details
    Optional query param: ?day=7 to get records from today to previous 7 days
    """
    def get(self, request, shop_id):
        try:
            shop = Shop.objects.get(id=shop_id)
        except Shop.DoesNotExist:
            return Response(
                {"detail": f"Shop with id {shop_id} not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        day_param = request.query_params.get('day')
        if day_param:
            try:
                days = int(day_param)
                if days < 0:
                    raise ValueError
            except ValueError:
                return Response(
                    {"detail": "Invalid 'day' parameter. Must be a non-negative integer."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            # Calculate the date from which to filter
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days - 1)
            # Make timezone aware if your project uses timezone-aware datetimes
            start_date = make_aware(start_date)
            end_date = make_aware(end_date)
            
            revenues = Revenue.objects.filter(
                shop=shop,
                timestamp__range=(start_date, end_date)
            ).order_by('-timestamp')
        else:
            revenues = Revenue.objects.filter(shop=shop).order_by('-timestamp')

        # Total revenue (all time, not filtered)
        total_revenue = Revenue.objects.filter(shop=shop).aggregate(
            total=Sum('revenue')
        )['total'] or 0

        serializer = RevenueSerializer(revenues, many=True)
        return Response(
            {
                "total_revenue": total_revenue,
                "revenues": serializer.data
            },
            status=status.HTTP_200_OK
        )
    
class GrowthSuggestionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        shop_id = request.query_params.get("shop_id")
        if not shop_id:
            return Response({"detail": "shop_id is required"}, status=400)

        suggestions = generate_growth_suggestions(shop_id=shop_id)
        serializer = SuggestionSerializer(suggestions, many=True)
        return Response(serializer.data)

class CouponListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, IsOwnerRole]  # Only owners

    def get(self, request):
        # Get coupons only for shops owned by the logged-in user
        coupons = Coupon.objects.filter(shop__owner=request.user)
        serializer = CouponSerializer(coupons, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = CouponSerializer(data=request.data)
        if serializer.is_valid():
            shop = serializer.validated_data.get('shop')
            # Verify shop belongs to this owner
            if shop.owner != request.user:
                return Response(
                    {"detail": "You can only create coupons for your own shop."},
                    status=status.HTTP_403_FORBIDDEN
                )
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CouponRetrieveUpdateDestroyAPIView(APIView):
    permission_classes = [IsAuthenticated, IsOwnerRole]

    def get_object(self, coupon_id):
        try:
            return Coupon.objects.get(id=coupon_id)
        except Coupon.DoesNotExist:
            return None

    def get(self, request, coupon_id):
        coupon = self.get_object(coupon_id)
        if not coupon:
            return Response({"detail": "Coupon not found"}, status=status.HTTP_404_NOT_FOUND)

        if coupon.shop.owner != request.user:
            return Response(
                {"detail": "You can only view coupons from your own shop."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = CouponSerializer(coupon)
        return Response(serializer.data)

    def patch(self, request, coupon_id):
        coupon = self.get_object(coupon_id)
        if not coupon:
            return Response({"detail": "Coupon not found"}, status=status.HTTP_404_NOT_FOUND)

        if coupon.shop.owner != request.user:
            return Response(
                {"detail": "You can only update coupons for your own shop."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = CouponSerializer(coupon, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, coupon_id):
        coupon = self.get_object(coupon_id)
        if not coupon:
            return Response({"detail": "Coupon not found"}, status=status.HTTP_404_NOT_FOUND)

        if coupon.shop.owner != request.user:
            return Response(
                {"detail": "You can only delete coupons for your own shop."},
                status=status.HTTP_403_FORBIDDEN
            )

        coupon.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class UserCouponRetrieveAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserCouponRetrieveSerializer(data=request.query_params)
        if serializer.is_valid():
            coupons = serializer.validated_data['coupons']
            output_serializer = CouponSerializer(coupons, many=True)
            return Response(output_serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class BestServicePerShopView(APIView):
    def get(self, request, shop_id):
        # Find service with most completed bookings for given shop
        best_service_data = (
            Booking.objects
            .filter(status="completed", shop_id=shop_id)
            .values('slot__service_id')
            .annotate(total_bookings=Count('id'))
            .order_by('-total_bookings')
            .first()
        )

        if not best_service_data:
            return Response({"detail": "No completed bookings found for this shop."}, status=status.HTTP_404_NOT_FOUND)

        service_id = best_service_data['slot__service_id']

        try:
            service = Service.objects.get(id=service_id)
        except Service.DoesNotExist:
            return Response({"detail": "Service not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ServiceSerializer(service, context={"request": request})
        result = serializer.data
        result['total_bookings'] = best_service_data['total_bookings']  # add bookings count

        return Response(result, status=status.HTTP_200_OK)


class PerformanceAnalyticsView(APIView):
    permission_classes = [IsAuthenticated, IsOwnerRole]

    def get(self, request):
        shop = get_object_or_404(Shop, owner=request.user)

        subscription = getattr(shop, 'subscription', None)
        if not subscription or not subscription.plan:
            return Response({"detail": "No active subscription found."}, status=status.HTTP_403_FORBIDDEN)

        plan = getattr(subscription.plan, 'performance_analytics', 'none')

        if plan == 'none':
            return Response({"detail": "No analytics available for your current plan."}, status=status.HTTP_403_FORBIDDEN)

        analytics, _ = PerformanceAnalytics.objects.get_or_create(shop=shop)
        serializer = PerformanceAnalyticsSerializer(analytics, context={'plan': plan})
        return Response(serializer.data, status=status.HTTP_200_OK)


class AIReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Return a weekly-style AI report using fields that actually exist:
        - PerformanceAnalytics: total_bookings, total_revenue, top_service, updated_at
        - AutoFillLog: count filled no-shows (last 7 days)
        - Slot: forecast open slots (next 7 days)
        """
        try:
            shop = request.user.shop
        except Shop.DoesNotExist:
            return Response({"error": "Shop not found."}, status=status.HTTP_404_NOT_FOUND)

        # latest analytics row by timestamp you actually have
        latest = (
            PerformanceAnalytics.objects
            .filter(shop=shop)
            .order_by('-updated_at')
            .first()
        )
        if not latest:
            return Response({"error": "No AI report available yet."}, status=status.HTTP_404_NOT_FOUND)

        now = timezone.now()
        week_ago = now - timedelta(days=7)
        next_week = now + timedelta(days=7)

        # no-shows filled automatically (use AutoFillLog as proxy)
        # count any log with a successfully filled booking over the last week
        filled_noshows = AutoFillLog.objects.filter(
            shop=shop,
            created_at__gte=week_ago,
            filled_by_booking__isnull=False
        ).count()

        # simple forecast: count open slots in the next 7 days
        open_slots = Slot.objects.filter(
            shop=shop,
            start_time__gt=now,
            start_time__lte=next_week,
            capacity_left__gt=0
        ).count()

        # map to your AI UI schema
        data = {
            "total_appointments": latest.total_bookings or 0,
            "total_revenue": float(latest.total_revenue or 0),
            "no_shows_filled": filled_noshows,
            "top_selling_service": latest.top_service or "-",
            "forecast_summary": f"You’ve got {open_slots} open slots next week — let’s fill them.",
            "motivational_nudge": "You’re building something bigger — let’s keep it rolling.",
            "updated_at": latest.updated_at,
            # nice to have for the app header/avatar
            "ai_partner_name": shop.ai_partner_name or "Amara",
        }
        return Response(data, status=status.HTTP_200_OK)

    def post(self, request):
        """
        Save the chosen AI partner for the authenticated user's shop.
        """
        partner_name = request.data.get("partner_name")
        if partner_name not in {"Malik", "Amara", "Dre", "Zuri"}:
            return Response({"error": "Invalid partner name."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            shop = request.user.shop
        except Shop.DoesNotExist:
            return Response({"error": "Shop not found."}, status=status.HTTP_404_NOT_FOUND)

        shop.ai_partner_name = partner_name
        shop.save(update_fields=["ai_partner_name"])
        return Response({"success": True, "partner_name": partner_name}, status=status.HTTP_200_OK)
    
# api/views.py

class LatestWeeklySummaryView(APIView):
    """
    GET /weekly-summary/latest/
    Returns the most recent WeeklySummary for the logged-in provider.
    Used by the Flutter 'Weekly Recap' screen.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # Assumption: 1 owner ↔ 1 shop. If you support multiple shops per owner,
        # filter by ?shop_id=... instead.
        shop = Shop.objects.filter(owner=user).first()
        if not shop:
            return Response(
                {"detail": "No shop found for this user."},
                status=status.HTTP_404_NOT_FOUND,
            )

        summary = (
            WeeklySummary.objects
            .filter(shop=shop)
            .order_by("-week_end_date", "-created_at")
            .first()
        )

        if not summary:
            return Response(
                {"detail": "No weekly summary available yet."},
                status=status.HTTP_404_NOT_FOUND,
            )

        data = WeeklySummarySerializer(summary).data
        return Response(data, status=status.HTTP_200_OK)
    

# -------------------------------
# 1️⃣ Generate Marketing Caption  (FIXED)
# -------------------------------
class GenerateMarketingCaptionView(APIView):
    """
    Customer-focused IG caption with heavy, AI-ish variety.
    Deterministic randomness (seeded) so the same week/service yields the same copy.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = WeeklySummaryActionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        summary_id = ser.validated_data["summary_id"]
        preview_only = ser.validated_data.get("preview_only", False)

        shop = getattr(request.user, "shop", None)
        if not shop:
            return Response({"detail": "Shop not found."}, status=status.HTTP_404_NOT_FOUND)
        summary = get_object_or_404(WeeklySummary, id=summary_id, shop=shop)

        # ----- Choose service (prefer weekly top, else best rated, else any) -----
        service = None
        if summary.top_service:
            service = Service.objects.filter(shop=shop, title__iexact=summary.top_service).first()
        if not service:
            service = (
                Service.objects.filter(shop=shop, is_active=True)
                .annotate(avg_rating=Avg("ratings__rating"))
                .order_by("-avg_rating", "-id")
                .first()
                or Service.objects.filter(shop=shop, is_active=True).first()
            )
        if not service:
            return Response({"detail": "No active services found for this shop."},
                            status=status.HTTP_400_BAD_REQUEST)

        # ----- Personalization facts -----
        base_price = service.discount_price if (service.discount_price and service.discount_price > 0) else service.price

        rating_agg = RatingReview.objects.filter(service=service).aggregate(avg=Avg("rating"), cnt=Count("id"))
        avg_rating = (rating_agg.get("avg") or 0)
        review_count = (rating_agg.get("cnt") or 0)

        weekly_count = None
        if summary.top_service and service.title.lower() == (summary.top_service or "").lower():
            weekly_count = summary.top_service_count or None

        now = timezone.now()
        next_slot = (
            Slot.objects.filter(shop=shop, service=service, start_time__gte=now, capacity_left__gt=0)
            .order_by("start_time")
            .first()
        )
        next_slot_str = None
        if next_slot:
            try:
                local_dt = timezone.localtime(next_slot.start_time)
            except Exception:
                local_dt = next_slot.start_time
            # Example: Fri, Nov 7 • 3:30 PM
            # (portable fallback if %-d %-I isn’t supported)
            fmt = "%a, %b %d • %I:%M %p"
            next_slot_str = local_dt.strftime(fmt).replace(" 0", " ")

        today = date.today()
        coupon = (
            Coupon.objects.filter(
                shop=shop,
                services__id=service.id,
                is_active=True,
                validity_date__gte=today,
            )
            .order_by("-in_percentage", "-amount")
            .first()
        )

        web_host = getattr(settings, "APP_WEB_HOST", "https://your-app.com").rstrip("/")
        utm = "utm=ig_revenue_booster"
        share_url = f"{web_host}/services/{service.id}?{utm}&shop_id={shop.id}"
        deep_link = f"fidden://service/{service.id}?shop_id={shop.id}"

        link_for_caption = deep_link

        def money(v):
            try:
                return f"৳{int(v):,}"
            except Exception:
                return f"৳{v}"

        def coupon_line(c):
            if not c:
                return ""
            if c.in_percentage:
                return f"Use code **{c.code}** to save {int(c.amount)}% (limited time)."
            return f"Use code **{c.code}** to save {money(c.amount)} (limited time)."

        cat = (getattr(getattr(service, "category", None), "name", "") or "")
        city = (shop.location or "").split(",")[0].strip() if shop.location else ""

        # ----- Deterministic RNG for variety -----
        rng_seed = f"{summary.id}-{service.id}-{summary.week_end_date.isoformat()}"
        rng = random.Random(hash(rng_seed))

        # ----- Hashtags -----
        base_tags = [
            "#BookNow", "#SelfCare", "#FreshLook", "#PamperYourself", "#LocalFav",
            "#LimitedSlots", "#TreatYourself", "#LookGoodFeelGood", "#TimeForYou", "#GlowDay",
        ]
        cat_map = {
            "Hair": ["#HairCare", "#Haircut", "#SalonVibes", "#StyleRefresh"],
            "Beauty": ["#BeautyTime", "#GlowUp", "#SkinCare", "#BeautyBoost"],
            "Spa": ["#SpaDay", "#Relax", "#Wellness", "#Unwind"],
            "Nails": ["#NailArt", "#Manicure", "#NailCare", "#PolishPerfection"],
            "Fitness": ["#Fitness", "#Recovery", "#Wellbeing", "#MoveBetter"],
        }
        cat_key = next((k for k in cat_map if k.lower() in cat.lower()), None)
        cat_tags = cat_map.get(cat_key, [])
        cat = (getattr(getattr(service, "category", None), "name", "") or "")
        raw_city = (shop.location or "").split(",")[0].strip() if shop.location else ""
        def _safe_city_tag(s: str):
            if not s:
                return None
            # if any digit is present, assume it's not a clean city name (likely coords or address w/ numbers)
            if any(ch.isdigit() for ch in s):
                return None
            return f"#{''.join(s.title().split())}"

        city_tag = _safe_city_tag(raw_city)

        tag_pick = rng.sample(base_tags, k=min(3, len(base_tags))) + rng.sample(cat_tags, k=min(2, len(cat_tags)))
        if city_tag and rng.random() < 0.7:
            tag_pick.append(city_tag)
        tag_pick = tag_pick[: rng.randint(3, 6)]
        hashtags = " ".join(tag_pick)

        # ----- Persona & tone bits (expanded) -----
        ai_name = shop.ai_partner_name or "Amara"
        openers = [
            f"Hi, I’m {ai_name} — your AI booking buddy 🤖",
            f"{ai_name} here — I found something you’ll love ✨",
            f"Your AI concierge {ai_name} checking in 💬",
            f"Psst… {ai_name} found a perfect pick for you 👀",
            f"{ai_name} (AI) with a quick tip for your next self-care moment 💡",
            f"From your AI assistant {ai_name}: a little upgrade for your week 🚀",
            f"Curated by {ai_name} (AI) for you 🌟",
            f"{ai_name} here — because great days start with great bookings 😊",
            f"Small nudge from {ai_name}: make time for you today 💖",
            f"{ai_name} says: treat yourself, you’ve earned it 🌿",
            f"A quick rec from {ai_name} — tailored to you 🎯",
            f"Your timeline called. {ai_name} answered with a glow-up ✨",
            f"{ai_name} again — I’m holding a spot you’ll want ⏳",
            f"{ai_name} here. Signal detected: pamper mode ✅",
            f"{ai_name} speaking: this one’s trending for a reason 🔥",
        ]
        opener = rng.choice(openers)

        # ----- Value props (dynamic facts → bullet lines) -----
        value_props = []
        if weekly_count and weekly_count > 0:
            times = f"{weekly_count} time{'s' if weekly_count != 1 else ''}"
            value_props.append(f"Our community loved it — booked **{times}** this week.")
        if avg_rating and review_count:
            star = f"{avg_rating:.1f}★" if avg_rating else "⭐️"
            value_props.append(f"Rated **{star}** by {review_count}+ clients.")
        if base_price:
            value_props.append(f"Starts at **{money(base_price)}**.")
        if next_slot_str:
            value_props.append(f"Next open slot: **{next_slot_str}**.")
        if coupon:
            value_props.append(coupon_line(coupon))
        if not value_props:
            value_props.append("Limited spots this week. Don’t miss out!")

        # Bullet styles & bridges
        bullet_styles = [
            ("- ", "\n"),
            ("• ", "\n"),
            ("— ", "\n"),
            ("✅ ", "\n"),
            ("✨ ", "\n"),
        ]
        bullet_prefix, bullet_join = rng.choice(bullet_styles)

        bridges = [
            "Why it’s a great pick:",
            "Clients are choosing this for a reason:",
            "Here’s what makes it worth it:",
            "Quick highlights:",
            "Top reasons to book:",
            "Why you’ll love it:",
        ]
        bridge = rng.choice(bridges)

        bullets = bullet_join.join(f"{bullet_prefix}{vp}" for vp in value_props)

        # ----- CTA & FOMO variants -----
        ctas = [
            "Book in a few taps:",
            "Secure your spot now:",
            "Lock this in today:",
            "Tap to view details & book:",
            "Ready when you are — book now:",
            "Let’s do this — reserve your time:",
            "Your moment awaits:",
        ]
        cta = rng.choice(ctas)

        fm_variants = [
            "Spots move fast on weekends ⏳",
            "Only a few openings left this week ⌛",
            "Early birds get the best times 🐦",
            "Treat yourself before the rush 💫",
            "Perfect for a mid-week reset 🌙",
        ]
        fomo_line = rng.choice(fm_variants) if rng.random() < 0.7 else None

        ps_variants = [
            "P.S. I’ll remind you before your slot — I’ve got you. 🤝",
            "P.S. You can reschedule from your profile anytime.",
            "P.S. Got a friend? Share this and go together!",
            "P.S. New here? Creating an account takes ~30 seconds.",
        ]
        ps_line = rng.choice(ps_variants) if rng.random() < 0.45 else None

        # ----- Template shells (more shapes) -----
        name = service.title or "Our top service"
        shells = [
            # 1) Classic opener + bridge + bullets + CTA
            "{opener}\n\n**{name}** is trending this week 🔥\n{bridge}\n{bullets}\n\n{cta}\n{url}\n\n{hashtags}",

            # 2) Question hook + bullets
            "Thinking about **{name}**? ✨\n{bridge}\n{bullets}\n\n{cta} {url}\n\n{hashtags}",

            # 3) Minimalist vibe
            "**{name}** — the glow-up pick ✨\n{bullets}\n\n{cta} {url}\n\n{hashtags}",

            # 4) Concierge voice
            "{opener}\nYour self-care pick: **{name}** 🌿\n{bullets}\n\n{cta}\n{url}\n\n{hashtags}",

            # 5) Social proof lead
            "{opener}\nClients can’t stop booking **{name}** 💬\n{bridge}\n{bullets}\n\n{cta}\n{url}\n\n{hashtags}",

            # 6) Short & punchy
            "**{name}**. Little time, big impact. ⚡\n{bullets}\n\n{cta} {url}\n\n{hashtags}",

            # 7) Dialogue vibe
            "{opener}\nLet me save you a scroll — try **{name}** today 🙌\n{bridge}\n{bullets}\n\n{cta}\n{url}\n\n{hashtags}",

            # 8) Momentum / energy
            "Ready for **{name}**? Let’s make it happen 🚀\n{bullets}\n\n{cta}\n{url}\n\n{hashtags}",

            # 9) Care / nurture tone
            "Gentle nudge from {ai_name}: book **{name}** and breathe a little easier today 💖\n{bullets}\n\n{cta}\n{url}\n\n{hashtags}",

            # 10) “List-first”
            "{opener}\nTop reasons **{name}** is a win:\n{bullets}\n\n{cta} {url}\n\n{hashtags}",
        ]
        shell = rng.choice(shells)

        # Build caption
        caption = shell.format(
            opener=opener,
            name=name,
            bridge=bridge,
            bullets=bullets,
            cta=cta,
            url=link_for_caption,
            hashtags=hashtags,
            ai_name=ai_name,
        )

        if fomo_line:
            caption += f"\n\n{fomo_line}"
        if coupon and rng.random() < 0.9:
            caption += "\n\n" + coupon_line(coupon)
        if ps_line:
            caption += f"\n\n{ps_line}"

        # Persist channel delivery marker (only when not previewing)
        if not preview_only:
            channels = set(summary.delivered_channels or [])
            channels.add("ig_caption")
            summary.delivered_channels = sorted(list(channels))
            summary.save(update_fields=["delivered_channels"])

        return Response(
            {
                "ok": True,
                "caption": caption,
                "share_url": share_url,
                "deep_link": deep_link,
                "preview_only": preview_only,
            },
            status=status.HTTP_200_OK,
        )

# -------------------------------
# 2️⃣ Send Retention Email
# -------------------------------
class SendLoyaltyEmailView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = WeeklySummaryActionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        summary_id = ser.validated_data["summary_id"]
        preview_only = ser.validated_data["preview_only"]

        shop = getattr(request.user, "shop", None)
        if not shop:
            return Response({"detail": "Shop not found."}, status=status.HTTP_404_NOT_FOUND)

        summary = get_object_or_404(WeeklySummary, id=summary_id, shop=shop)

        # ---------- 1) Create 10% coupon valid 7 days ----------
        valid_until = timezone.now().date() + timedelta(days=7)

        with transaction.atomic():
            coupon = Coupon.objects.create(
                shop=shop,
                description="Next Week Loyalty Boost (10% off)",
                amount=10,
                in_percentage=True,
                validity_date=valid_until,
                is_active=not preview_only,  # keep inactive for previews
            )

        # ---------- 2) Build audience ----------
        # Clients who completed during the summary window…
        recent_clients = (
            Booking.objects.filter(
                shop=shop,
                status="completed",
                created_at__date__gte=summary.week_start_date,
                created_at__date__lte=summary.week_end_date,
            )
            .values_list("user__email", flat=True)
            .distinct()
        )

        # …who have NOT rebooked since the summary ended
        rebooked = set(
            Booking.objects.filter(
                shop=shop,
                created_at__date__gte=summary.week_end_date,
            )
            .values_list("user__email", flat=True)
            .distinct()
        )

        target_emails = sorted(
            {e.strip().lower() for e in recent_clients if e and e.strip()} - {e for e in rebooked if e}
        )

        # ---------- 3) Compose message ----------
        subj_base = f"Next Week Loyalty Boost from {shop.name} 💈"
        subject = f"[PREVIEW] {subj_base}" if preview_only else subj_base

        # Deep link for ShopDetailsScreen
        booking_url = f"fidden://shop/{shop.id}?coupon={coupon.code}"

        text_message = (
            f"Hey there!\n\n"
            f"We miss you at {shop.name}! As a thank-you, here's a 10% off coupon if you book within the next 7 days.\n\n"
            f"Use code {coupon.code} at checkout.\n"
            f"Valid until {valid_until.strftime('%b %d, %Y')}.\n\n"
            f"Book now 👉 {booking_url}\n\n"
            f"See you soon!\n— {shop.name}"
        )

        html_message = f"""
            <p>Hey there!</p>
            <p>We miss you at <strong>{shop.name}</strong>! As a thank-you, here’s a <strong>10% off</strong> coupon if you book within the next 7 days.</p>
            <p><strong>Code:</strong> {coupon.code}<br/>
               <strong>Valid until:</strong> {valid_until.strftime('%b %d, %Y')}</p>
            <p><a href="{booking_url}">Book now</a></p>
            <p>See you soon!<br/>— {shop.name}</p>
        """

        # ---------- 4) Send (or preview) ----------
        if not preview_only and target_emails:
            # Send in a single connection for performance; batch in chunks of 100
            sent = 0
            chunk_size = 100
            from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@your-app.com")
            reply_to = [getattr(settings, "SUPPORT_EMAIL", from_email)]

            with get_connection() as conn:
                for i in range(0, len(target_emails), chunk_size):
                    batch = target_emails[i : i + chunk_size]
                    messages = []
                    for email in batch:
                        msg = EmailMultiAlternatives(
                            subject=subject,
                            body=text_message,
                            from_email=from_email,
                            to=[email],
                            reply_to=reply_to,
                            connection=conn,
                        )
                        msg.attach_alternative(html_message, "text/html")
                        messages.append(msg)
                    try:
                        sent += conn.send_messages(messages) or 0
                    except Exception:
                        logger.exception("Failed sending loyalty emails batch for shop=%s", shop.id)

            # stamp channel once delivered
            delivered = set(summary.delivered_channels or [])
            delivered.add("email_retention")
            summary.delivered_channels = list(delivered)
            summary.save(update_fields=["delivered_channels"])

            return Response(
                {
                    "ok": True,
                    "coupon_code": coupon.code,
                    "valid_until": str(valid_until),
                    "subject": subject,
                    "audience_size": len(target_emails),
                    "sent": sent,
                    "preview_only": False,
                }
            )

        # PREVIEW response (no delivery)
        return Response(
            {
                "ok": True,
                "coupon_code": coupon.code,
                "valid_until": str(valid_until),
                "subject": subject,
                "preview_text": text_message,
                "preview_html": html_message,
                "audience_size": len(target_emails),
                "preview_only": True,
            }
        )
