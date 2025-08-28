from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Avg

from .models import (
    Shop, 
    Service, 
    RatingReview, 
    ServiceCategory, 
    Slot, 
    SlotBooking, 
    FavoriteShop,
    Promotion
)
from .serializers import (
    ShopSerializer, 
    ServiceSerializer, 
    RatingReviewSerializer, 
    ServiceCategorySerializer, 
    SlotSerializer, 
    SlotBookingSerializer,
    ShopListSerializer, 
    ShopDetailSerializer, 
    ServiceListSerializer,
    ServiceDetailSerializer,
    FavoriteShopSerializer,
    PromotionSerializer
)
from .permissions import IsOwnerAndOwnerRole, IsOwnerRole

from math import radians, cos, sin, asin, sqrt
from django.db.models.expressions import Func
from datetime import datetime
from django.db import transaction
from django.utils import timezone
from django.db.models import Avg, Count, Q, Value, FloatField, F
from django.db.models.functions import Coalesce
from .pagination import ServicesCursorPagination

from urllib.parse import urlencode
from collections import OrderedDict



class ShopListCreateView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]

    def get(self, request):
        user = request.user
        if getattr(user, 'role', None) != 'owner':
            return Response({"detail": "You do not have a shop."}, status=status.HTTP_403_FORBIDDEN)

        shop = Shop.objects.filter(owner=user).first()
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
            return Response(ShopSerializer(shop, context={'request': request}).data, status=status.HTTP_201_CREATED)
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
            shop = serializer.save(owner=request.user)
            return Response(ShopSerializer(shop, context={'request': request}).data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        shop = self.get_object(pk)
        serializer = ShopSerializer(shop, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            shop = serializer.save(owner=request.user)
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
        serializer = ServiceCategorySerializer(categories, many=True)
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

        shops_qs = Shop.objects.all()
        if search_query:
            shops_qs = shops_qs.filter(
                Q(name__iregex=search_query) | Q(address__iregex=search_query)
            )

        shops_qs = shops_qs.annotate(
            avg_rating=Coalesce(Avg('ratings__rating'), Value(0.0, output_field=FloatField())),
            review_count=Count(
                'ratings',
                filter=Q(ratings__review__isnull=False) & ~Q(ratings__review__exact='')
            )
        )

        # Sort by avg_rating and review_count first; distance sorted later
        shops_qs = shops_qs.order_by('-avg_rating', '-review_count')

        # Serialize with distance and badge
        serializer = ShopListSerializer(
            shops_qs, many=True, context={"request": request, "user_location": user_location}
        )
        shops_list = serializer.data

        # Sort by distance → avg_rating → review_count
        shops_list = sorted(
            shops_list,
            key=lambda x: (x["distance"] if x["distance"] is not None else float("inf"),
                           -x["avg_rating"], -x["review_count"])
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


        serializer = ShopDetailSerializer(shop, context={'request': request})
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
            Service.objects.filter(is_active=True)
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
                    user_lon, user_lat = map(float, user_location.split(","))
                    shop_lon, shop_lat = map(float, service.shop.location.split(","))
                except Exception:
                    return float("inf")
                # Haversine formula
                lon1, lat1, lon2, lat2 = map(radians, [user_lon, user_lat, shop_lon, shop_lat])
                dlon = lon2 - lon1
                dlat = lat2 - lat1
                a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
                c = 2 * asin(sqrt(a))
                km = 6371 * c
                return km * 1000  # meters

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
        user_location = request.data.get("location")  # optional: "lon,lat"
        favorites = FavoriteShop.objects.filter(user=request.user).select_related('shop')
        serializer = FavoriteShopSerializer(favorites, many=True, context={'request': request, 'user_location': user_location})
        return Response(serializer.data, status=status.HTTP_200_OK)

class PromotionListView(APIView):
    """
    GET: Retrieve all active promotions
    """
    def get(self, request):
        promotions = Promotion.objects.filter(is_active=True).order_by('-created_at')
        serializer = PromotionSerializer(promotions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)