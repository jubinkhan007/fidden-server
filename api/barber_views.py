# Barber Dashboard Views

from datetime import date
from django.utils import timezone
from django.db.models import Q, Count, Sum
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
