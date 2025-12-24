# Barber Dashboard Views

from datetime import date
from django.utils import timezone
from django.db.models import Q, Count, Sum, Max
from django.db import models
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from .models import Shop
from .permissions import IsOwnerRole
from payments.models import Booking
from .barber_serializers import BarberAppointmentSerializer, BarberNoShowSerializer

class TodayAppointmentsView(APIView):
    """
    Get today's appointments for shop owner
    Supports date query param for other days
    Supports niche query param for filtering by service niche
    """
    permission_classes = [IsAuthenticated, IsOwnerRole]
    
    # Keywords for niches
    NICHE_KEYWORDS = {
        'barber': ['barber', 'haircut', 'hair cut', 'fade', 'beard', 'shave', 'trim', 'lineup', 'taper'],
        'tattoo': ['tattoo', 'ink', 'piercing', 'body art', 'tat'],
        'tattoo_artist': ['tattoo', 'ink', 'piercing', 'body art', 'tat'],
        'esthetician': ['facial', 'skin', 'peel', 'microderm', 'wax', 'lash', 'brow', 'spa'],
        'massage': ['massage', 'deep tissue', 'swedish', 'hot stone', 'body work', 'reflexology'],
        'massage_therapist': ['massage', 'deep tissue', 'swedish', 'hot stone', 'body work', 'reflexology'],
        'hair': ['hair', 'color', 'highlight', 'loc', 'braid', 'weave', 'style', 'blow'],
        'hairstylist': ['hair', 'color', 'highlight', 'loc', 'braid', 'weave', 'style', 'blow'],
        'nail': ['nail', 'manicure', 'pedicure', 'gel', 'acrylic', 'polish'],
        'nail_tech': ['nail', 'manicure', 'pedicure', 'gel', 'acrylic', 'polish'],
        'makeup': ['makeup', 'make up', 'bridal', 'glam', 'mua', 'look'],
        'makeup_artist': ['makeup', 'make up', 'bridal', 'glam', 'mua', 'look'],
    }
    
    # Niche to service type field mapping
    NICHE_FIELD_MAPPING = {
        'esthetician': 'esthetician_service_type',
        'massage': 'esthetician_service_type',
        'hair': 'hair_service_type',
        'hairstylist': 'hair_service_type',
        'nail': 'nail_style_type',
        'nail_tech': 'nail_style_type',
        'makeup': 'look_type',
        'makeup_artist': 'look_type',
    }
    
    def get(self, request):
        shop = get_object_or_404(Shop, owner=request.user)
        
        # Get date from query params (default: today)
        date_param = request.query_params.get('date')
        if date_param:
            try:
                target_date = timezone.datetime.strptime(date_param, '%Y-%m-%d').date()
            except ValueError:
                target_date = timezone.now().date()
        else:
            target_date = timezone.now().date()
        
        # Get niche filter
        niche = request.query_params.get('niche')
        
        # Create UTC date range for proper timezone-independent filtering
        from datetime import datetime, time, timezone as dt_tz
        import pytz
        start_of_day_utc = datetime.combine(target_date, time.min, tzinfo=pytz.UTC)
        end_of_day_utc = datetime.combine(target_date, time.max, tzinfo=pytz.UTC)
        
        # Get all bookings for the target date (using UTC range)
        bookings = Booking.objects.filter(
            shop=shop,
            slot__start_time__gte=start_of_day_utc,
            slot__start_time__lte=end_of_day_utc
        ).select_related('user', 'slot', 'slot__service', 'slot__service__category').order_by('slot__start_time')
        
        # Apply niche filter if provided
        if niche:
            field = self.NICHE_FIELD_MAPPING.get(niche)
            keywords = self.NICHE_KEYWORDS.get(niche, [])
            
            if field:
                # Filter by service type field (non-empty value)
                filter_kwargs = {f'slot__service__{field}__isnull': False}
                exclude_kwargs = {f'slot__service__{field}': ''}
                field_bookings = bookings.filter(**filter_kwargs).exclude(**exclude_kwargs)
                
                # Also include keyword matches (fallback)
                if keywords:
                    q = Q()
                    for kw in keywords:
                        q |= Q(slot__service__title__icontains=kw)
                        q |= Q(slot__service__category__name__icontains=kw)
                    keyword_bookings = bookings.filter(q)
                    bookings = (field_bookings | keyword_bookings).distinct()
                else:
                    bookings = field_bookings
            elif keywords:
                # Keyword-only filtering (for barber, tattoo)
                q = Q()
                for kw in keywords:
                    q |= Q(slot__service__title__icontains=kw)
                    q |= Q(slot__service__category__name__icontains=kw)
                bookings = bookings.filter(q)
        
        serializer = BarberAppointmentSerializer(bookings, many=True)
        
        # Include summary statistics
        total_count = bookings.count()
        confirmed_count = bookings.filter(status='active').count()
        completed_count = bookings.filter(status='completed').count()
        cancelled_count = bookings.filter(status='cancelled').count()
        no_show_count = bookings.filter(status='no-show').count()
        
        return Response({
            'date': target_date.isoformat(),
            'count': total_count,
            'niche': niche,
            'stats': {
                'confirmed': confirmed_count,
                'completed': completed_count,
                'cancelled': cancelled_count,
                'no_show': no_show_count
            },
            'appointments': serializer.data
        }, status=status.HTTP_200_OK)


class DailyRevenueView(APIView):
    """
    Get daily revenue with optional date and service_type filter.
    
    Query params:
    - date: YYYY-MM-DD (default: today)
    - service_type: Filter by service type (e.g., facial, massage, tattoo)
    - niche: Filter by niche (esthetician, massage, hair, barber, tattoo, nail, makeup)
    """
    permission_classes = [IsAuthenticated, IsOwnerRole]
    
    # Niche to service type field mapping (for niches with dedicated fields)
    NICHE_FIELD_MAPPING = {
        'esthetician': 'esthetician_service_type',
        'massage': 'esthetician_service_type',  # massage is under esthetician_service_type
        'hair': 'hair_service_type',
        'hairstylist': 'hair_service_type',
        'nail': 'nail_style_type',
        'nail_tech': 'nail_style_type',
        'makeup': 'look_type',
        'makeup_artist': 'look_type',
    }
    
    # Keywords for niches without dedicated service type fields
    NICHE_KEYWORDS = {
        'barber': ['barber', 'haircut', 'hair cut', 'fade', 'beard', 'shave', 'trim', 'lineup', 'taper'],
        'tattoo': ['tattoo', 'ink', 'piercing', 'body art', 'tat'],
        'tattoo_artist': ['tattoo', 'ink', 'piercing', 'body art', 'tat'],
        'esthetician': ['facial', 'skin', 'peel', 'microderm', 'wax', 'lash', 'brow', 'spa'],
        'massage': ['massage', 'deep tissue', 'swedish', 'hot stone', 'body work', 'reflexology'],
        'massage_therapist': ['massage', 'deep tissue', 'swedish', 'hot stone', 'body work', 'reflexology'],
        'hair': ['hair', 'color', 'highlight', 'loc', 'braid', 'weave', 'style', 'blow'],
        'hairstylist': ['hair', 'color', 'highlight', 'loc', 'braid', 'weave', 'style', 'blow'],
        'nail': ['nail', 'manicure', 'pedicure', 'gel', 'acrylic', 'polish'],
        'nail_tech': ['nail', 'manicure', 'pedicure', 'gel', 'acrylic', 'polish'],
        'makeup': ['makeup', 'make up', 'bridal', 'glam', 'mua', 'look'],
        'makeup_artist': ['makeup', 'make up', 'bridal', 'glam', 'mua', 'look'],
    }
    
    def get(self, request):
        shop = get_object_or_404(Shop, owner=request.user)
        
        # Get date from query params (default: today)
        date_param = request.query_params.get('date')
        if date_param:
            try:
                target_date = timezone.datetime.strptime(date_param, '%Y-%m-%d').date()
            except ValueError:
                target_date = timezone.now().date()
        else:
            target_date = timezone.now().date()
        
        # Get filter params
        service_type = request.query_params.get('service_type')
        niche = request.query_params.get('niche')
        
        # Create UTC date range for proper timezone-independent filtering
        # We want all bookings where start_time falls on target_date in UTC
        from datetime import datetime, time, timezone as dt_tz
        import pytz
        start_of_day_utc = datetime.combine(target_date, time.min, tzinfo=pytz.UTC)
        end_of_day_utc = datetime.combine(target_date, time.max, tzinfo=pytz.UTC)
        
        # Base booking queryset for the day (using UTC range)
        bookings = Booking.objects.filter(
            shop=shop,
            slot__start_time__gte=start_of_day_utc,
            slot__start_time__lte=end_of_day_utc,
            status__in=['active', 'completed']
        ).select_related('slot__service', 'slot__service__category')
        
        # Debug: log initial count
        import logging
        logger = logging.getLogger(__name__)
        initial_count = bookings.count()
        logger.info(f"DailyRevenueView: shop={shop.id}, date={target_date}, utc_range=[{start_of_day_utc}, {end_of_day_utc}], niche={niche}, initial_count={initial_count}")
        
        # Log all service titles for today's bookings
        for b in bookings:
            svc_title = b.slot.service.title if b.slot and b.slot.service else 'N/A'
            logger.info(f"  - Booking {b.id}: service='{svc_title}'")
        
        # Apply service_type filter if provided
        if service_type:
            bookings = bookings.filter(
                Q(slot__service__esthetician_service_type=service_type) |
                Q(slot__service__hair_service_type=service_type) |
                Q(slot__service__nail_style_type=service_type)
            )
        
        # Apply niche filter if provided
        if niche:
            field = self.NICHE_FIELD_MAPPING.get(niche)
            keywords = self.NICHE_KEYWORDS.get(niche, [])
            logger.info(f"DailyRevenueView: niche={niche}, field={field}, keywords={keywords}")
            
            if field:
                # Filter by service type field (non-empty value)
                filter_kwargs = {f'slot__service__{field}__isnull': False}
                exclude_kwargs = {f'slot__service__{field}': ''}
                field_bookings = bookings.filter(**filter_kwargs).exclude(**exclude_kwargs)
                field_count = field_bookings.count()
                logger.info(f"DailyRevenueView: field_bookings count={field_count}")
                
                # Also include keyword matches (fallback)
                if keywords:
                    q = Q()
                    for kw in keywords:
                        q |= Q(slot__service__title__icontains=kw)
                    keyword_bookings = bookings.filter(q)
                    keyword_count = keyword_bookings.count()
                    logger.info(f"DailyRevenueView: keyword_bookings count={keyword_count}")
                    # Combine both (field match OR keyword match)
                    bookings = (field_bookings | keyword_bookings).distinct()
                else:
                    bookings = field_bookings
            elif keywords:
                # Keyword-only filtering (for barber, tattoo)
                q = Q()
                for kw in keywords:
                    q |= Q(slot__service__title__icontains=kw)
                bookings = bookings.filter(q)
                logger.info(f"DailyRevenueView: after keyword filter, count={bookings.count()}")
        
        # This reflects what was actually paid (deposits + checkout payments)
        booking_count = bookings.count()
        logger.info(f"DailyRevenueView: final booking_count={booking_count}")
        
        # Sum actual payment amounts for these bookings
        from payments.models import Payment
        booking_ids = list(bookings.values_list('id', flat=True))
        
        # Get payments for these bookings that are in succeeded status
        payments = Payment.objects.filter(
            booking_id__in=booking_ids,
            status='succeeded'
        )
        
        # Log for debugging
        for p in payments:
            logger.info(f"  Payment id={p.id}, booking_id={p.booking_id}, amount={p.amount}")
        
        # Sum the 'amount' field directly - this is what was actually charged
        from django.db.models.functions import Coalesce
        from django.db.models import DecimalField, Value
        from decimal import Decimal
        
        daily_revenue = float(payments.aggregate(
            total=Coalesce(Sum('amount'), Value(Decimal('0')), output_field=DecimalField())
        )['total'] or 0)
        
        # Calculate average booking value
        avg_booking_value = (daily_revenue / booking_count) if booking_count > 0 else 0
        
        return Response({
            'date': target_date.isoformat(),
            'total_revenue': daily_revenue,
            'booking_count': booking_count,
            'average_booking_value': float(avg_booking_value),
            'filters_applied': {
                'service_type': service_type,
                'niche': niche
            }
        }, status=status.HTTP_200_OK)


class NoShowAlertsView(APIView):
    """
    Get recent no-show bookings
    Supports days query param (default: 7)
    """
    permission_classes = [IsAuthenticated, IsOwnerRole]
    
    def get(self, request):
        shop = get_object_or_404(Shop, owner=request.user)
        
        # Get days from query params (default: 7)
        days = int(request.query_params.get('days', 7))
        cutoff_date = timezone.now() - timezone.timedelta(days=days)
        
        # Get no-show bookings
        no_shows = Booking.objects.filter(
            shop=shop,
            status='no-show',
            slot__start_time__gte=cutoff_date
        ).select_related('user', 'slot', 'slot__service').order_by('-slot__start_time')
        
        serializer = BarberNoShowSerializer(no_shows, many=True)
        
        return Response({
            'count': no_shows.count(),
            'days': days,
            'no_shows': serializer.data
        }, status=status.HTTP_200_OK)


# ==========================================
# WALK-IN QUEUE VIEWS
# ==========================================
from rest_framework import viewsets
from .models import WalkInEntry, LoyaltyProgram, LoyaltyPoints
from .barber_serializers import WalkInEntrySerializer, LoyaltyProgramSerializer, LoyaltyPointsSerializer


class WalkInQueueView(APIView):
    """
    Get current walk-in queue for shop.
    Shows only waiting and in_service entries.
    """
    permission_classes = [IsAuthenticated, IsOwnerRole]
    
    def get(self, request):
        shop = get_object_or_404(Shop, owner=request.user)
        
        # Get today's walk-ins that are still active
        today = timezone.now().date()
        queue = WalkInEntry.objects.filter(
            shop=shop,
            status__in=['waiting', 'in_service'],
            joined_at__date=today
        ).select_related('user', 'service').order_by('position', 'joined_at')
        
        serializer = WalkInEntrySerializer(queue, many=True)
        
        # Stats
        waiting_count = queue.filter(status='waiting').count()
        in_service_count = queue.filter(status='in_service').count()
        
        return Response({
            'queue': serializer.data,
            'waiting_count': waiting_count,
            'in_service_count': in_service_count,
            'total_in_queue': queue.count()
        })
    
    def post(self, request):
        """Add a customer to the walk-in queue"""
        shop = get_object_or_404(Shop, owner=request.user)
        
        # Calculate position (next in queue)
        today = timezone.now().date()
        last_position = WalkInEntry.objects.filter(
            shop=shop,
            joined_at__date=today
        ).aggregate(max_pos=models.Max('position'))['max_pos'] or 0
        
        # Create walk-in entry
        serializer = WalkInEntrySerializer(data=request.data)
        if serializer.is_valid():
            walk_in = serializer.save(
                shop=shop,
                position=last_position + 1
            )
            # Estimate wait time (15 min per person in queue)
            waiting_count = WalkInEntry.objects.filter(
                shop=shop,
                status='waiting',
                joined_at__date=today
            ).count()
            walk_in.estimated_wait_minutes = waiting_count * 15
            walk_in.save()
            
            return Response(WalkInEntrySerializer(walk_in).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class WalkInEntryDetailView(APIView):
    """Update walk-in entry status (call, complete, no-show)"""
    permission_classes = [IsAuthenticated, IsOwnerRole]
    
    def get_object(self, pk, shop):
        return get_object_or_404(WalkInEntry, pk=pk, shop=shop)
    
    def patch(self, request, pk):
        shop = get_object_or_404(Shop, owner=request.user)
        entry = self.get_object(pk, shop)
        
        new_status = request.data.get('status')
        if new_status:
            entry.status = new_status
            if new_status == 'in_service':
                entry.called_at = timezone.now()
            elif new_status in ['completed', 'no_show', 'cancelled']:
                entry.completed_at = timezone.now()
            entry.save()
        
        return Response(WalkInEntrySerializer(entry).data)
    
    def delete(self, request, pk):
        shop = get_object_or_404(Shop, owner=request.user)
        entry = self.get_object(pk, shop)
        entry.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ==========================================
# LOYALTY PROGRAM VIEWS
# ==========================================

class LoyaltyProgramView(APIView):
    """
    Get or update shop's loyalty program settings
    """
    permission_classes = [IsAuthenticated, IsOwnerRole]
    
    def get(self, request):
        shop = get_object_or_404(Shop, owner=request.user)
        program, created = LoyaltyProgram.objects.get_or_create(shop=shop)
        return Response(LoyaltyProgramSerializer(program).data)
    
    def patch(self, request):
        shop = get_object_or_404(Shop, owner=request.user)
        program, created = LoyaltyProgram.objects.get_or_create(shop=shop)
        
        serializer = LoyaltyProgramSerializer(program, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoyaltyCustomersView(APIView):
    """
    List all customers with loyalty points for this shop
    """
    permission_classes = [IsAuthenticated, IsOwnerRole]
    
    def get(self, request):
        shop = get_object_or_404(Shop, owner=request.user)
        customers = LoyaltyPoints.objects.filter(
            shop=shop
        ).select_related('user').order_by('-points_balance')
        
        serializer = LoyaltyPointsSerializer(customers, many=True)
        return Response({
            'count': customers.count(),
            'customers': serializer.data
        })


class LoyaltyPointsAddView(APIView):
    """
    Add loyalty points to a customer after a purchase
    """
    permission_classes = [IsAuthenticated, IsOwnerRole]
    
    def post(self, request):
        shop = get_object_or_404(Shop, owner=request.user)
        
        user_id = request.data.get('user_id')
        amount_spent = float(request.data.get('amount_spent', 0))
        
        if not user_id or amount_spent <= 0:
            return Response(
                {'error': 'user_id and amount_spent required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get or create loyalty points for this customer
        from accounts.models import User
        user = get_object_or_404(User, id=user_id)
        
        loyalty_points, created = LoyaltyPoints.objects.get_or_create(
            shop=shop, user=user
        )
        
        # Get program settings
        try:
            program = shop.loyalty_program
        except LoyaltyProgram.DoesNotExist:
            return Response(
                {'error': 'Loyalty program not configured for this shop'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Add points
        points_earned = loyalty_points.add_points(amount_spent, program)
        
        return Response({
            'points_earned': points_earned,
            'new_balance': loyalty_points.points_balance,
            'can_redeem': loyalty_points.points_balance >= program.points_for_redemption
        })


class LoyaltyRedeemView(APIView):
    """
    Redeem loyalty points for a reward
    """
    permission_classes = [IsAuthenticated, IsOwnerRole]
    
    def post(self, request):
        shop = get_object_or_404(Shop, owner=request.user)
        
        user_id = request.data.get('user_id')
        if not user_id:
            return Response(
                {'error': 'user_id required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from accounts.models import User
        user = get_object_or_404(User, id=user_id)
        loyalty_points = get_object_or_404(LoyaltyPoints, shop=shop, user=user)
        
        try:
            program = shop.loyalty_program
        except LoyaltyProgram.DoesNotExist:
            return Response(
                {'error': 'Loyalty program not configured'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        success, reward_value = loyalty_points.redeem_points(program)
        
        if success:
            return Response({
                'success': True,
                'reward_type': program.reward_type,
                'reward_value': float(reward_value),
                'points_remaining': loyalty_points.points_balance
            })
        else:
            return Response({
                'success': False,
                'error': f'Not enough points. Need {program.points_for_redemption}, have {loyalty_points.points_balance}'
            }, status=status.HTTP_400_BAD_REQUEST)

