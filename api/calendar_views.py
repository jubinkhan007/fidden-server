from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db.models import F, Q
from django.utils import timezone
from datetime import datetime, time
import logging

from api.models import Shop, BlockedTime
from payments.models import Booking
from api.serializers_calendar import CalendarEventSerializer
from api.permissions import IsOwnerRole

logger = logging.getLogger(__name__)

class CalendarView(APIView):
    permission_classes = [IsAuthenticated, IsOwnerRole]

    def get(self, request):
        """
        GET /api/calendar/
        Returns unified list of bookings and blocked times for the calendar.
        """
        user = request.user
        
        # 1. Query Params
        shop_id = request.query_params.get('shop_id')
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        provider_id = request.query_params.get('provider_id')
        
        if not shop_id or not start_date_str or not end_date_str:
            return Response(
                {"detail": "Missing required params: shop_id, start_date, end_date"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. Permission Check (Owner owns this shop?)
        try:
            shop = Shop.objects.get(id=shop_id)
        except Shop.DoesNotExist:
            return Response({"detail": "Shop not found"}, status=status.HTTP_404_NOT_FOUND)

        # Ensure the requester owns the shop
        # (Assuming simple 1-to-1 or utilizing IsOwnerRole logic)
        if hasattr(user, 'shop') and user.shop.id != int(shop_id):
             return Response({"detail": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
        # If user.role is owner but has no shop, or mismatch?
        # IsOwnerRole checks user.role == 'owner'.
        # We assume strict ownership check here.
        if user.shop.id != int(shop_id):
             return Response({"detail": "You do not own this shop"}, status=status.HTTP_403_FORBIDDEN)

        # 3. Parse Dates
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except ValueError:
             return Response({"detail": "Invalid date format. Use YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST)

        # 4. Fetch Bookings
        # Filter by date range (overlap)
        # Booking has start_time and provider_busy_end (or total_end).
        # We want any booking that starts or intersects the range?
        # Typically calendar fetches by "start_time" within range for simple grid.
        
        bookings_qs = Booking.objects.filter(
            shop=shop,
            slot__start_time__date__gte=start_date,
            slot__start_time__date__lte=end_date
        ).select_related('slot', 'slot__service', 'user', 'provider', 'payment', 'shop')
        
        if provider_id:
            bookings_qs = bookings_qs.filter(provider_id=provider_id)
            
        # exclude late-cancel if desired? No, keep all statuses per requirements.
        
        # Alias fields to match 'start_at' / 'end_at' expected by serializer
        # Using slot.end_time for actual service duration (not provider_busy_end)
        bookings = bookings_qs.annotate(
            start_at=F('slot__start_time'),
            end_at=F('slot__end_time')
        )

        # 5. Fetch BlockedTime
        blocked_qs = BlockedTime.objects.filter(
            shop=shop,
            start_at__date__gte=start_date,
            start_at__date__lte=end_date
        ).select_related('provider')
        
        if provider_id:
            # Include specific provider blocks OR shop-wide blocks (provider=None)
            blocked_qs = blocked_qs.filter(Q(provider_id=provider_id) | Q(provider__isnull=True))
            
        # 6. Combine
        # Evaluate querysets to lists
        events_list = list(bookings) + list(blocked_qs)
        
        # Sort by start time (optional, UI usually handles it, but good for debug)
        # We need a unified key for sorting.
        # Booking has 'start_time', BlockedTime has 'start_at'.
        # We annotated 'start_at' on bookings.
        # But annotated fields exist on model instance after query.
        # BlockedTime already has 'start_at'.
        events_list.sort(key=lambda x: x.start_at)

        # 7. Serialize
        serializer = CalendarEventSerializer(events_list, many=True, context={'check_new_customer': True})
        
        return Response(serializer.data)
