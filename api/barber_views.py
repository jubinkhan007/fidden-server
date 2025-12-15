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
    """
    permission_classes = [IsAuthenticated, IsOwnerRole]
    
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
        
        # Get all bookings for the target date
        bookings = Booking.objects.filter(
            shop=shop,
            slot__start_time__date=target_date
        ).select_related('user', 'slot', 'slot__service').order_by('slot__start_time')
        
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
    Get daily revenue with optional date filter
    """
    permission_classes = [IsAuthenticated, IsOwnerRole]
    
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
        
        # Get revenue for the target date
        from .models import Revenue
        daily_revenue = Revenue.objects.filter(
            shop=shop,
            timestamp=target_date
        ).aggregate(total=Sum('revenue'))['total'] or 0
        
        # Get booking count for the day
        booking_count = Booking.objects.filter(
            shop=shop,
            slot__start_time__date=target_date,
            status__in=['active', 'completed']
        ).count()
        
        # Calculate average booking value
        avg_booking_value = (daily_revenue / booking_count) if booking_count > 0 else 0
        
        return Response({
            'date': target_date.isoformat(),
            'total_revenue': float(daily_revenue),
            'booking_count': booking_count,
            'average_booking_value': float(avg_booking_value)
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

