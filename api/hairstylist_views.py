# Hairstylist/Loctician Dashboard Views
from datetime import timedelta
from django.utils import timezone
from django.db.models import Sum, Q
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from .models import Shop, Service, ClientHairProfile, ProductRecommendation
from .permissions import IsOwnerAndOwnerRole
from .hairstylist_serializers import (
    ClientHairProfileSerializer, ProductRecommendationSerializer,
    PrepNotesSerializer, HairstylistDashboardSerializer
)
from payments.models import Booking


class HairstylistDashboardView(APIView):
    """Aggregated dashboard data for Hairstylist niche"""
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]
    
    def get(self, request):
        shop = get_object_or_404(Shop, owner=request.user)
        today = timezone.now().date()
        week_end = today + timedelta(days=7)
        
        # Today's appointments
        today_appointments = Booking.objects.filter(
            shop=shop,
            slot__start_time__date=today,
            status__in=['active', 'completed']
        ).count()
        
        # Week appointments (next 7 days)
        week_appointments = Booking.objects.filter(
            shop=shop,
            slot__start_time__date__gte=today,
            slot__start_time__date__lt=week_end,
            status__in=['active', 'completed']
        ).count()
        
        # Today's revenue
        from .models import Revenue
        today_revenue = Revenue.objects.filter(
            shop=shop,
            timestamp=today
        ).aggregate(total=Sum('revenue'))['total'] or 0
        
        # Client profiles count
        client_profiles = ClientHairProfile.objects.filter(shop=shop).count()
        
        # Product recommendations count
        product_recs = ProductRecommendation.objects.filter(shop=shop).count()
        
        # Services with consultation
        consultation_services = Service.objects.filter(
            shop=shop,
            includes_consultation=True,
            is_active=True
        ).count()
        
        return Response({
            'today_appointments_count': today_appointments,
            'week_appointments_count': week_appointments,
            'today_revenue': float(today_revenue),
            'client_profiles_count': client_profiles,
            'product_recommendations_count': product_recs,
            'consultation_services_count': consultation_services
        })


class WeeklyScheduleView(APIView):
    """Get appointments for the next 7 days"""
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]
    
    def get(self, request):
        shop = get_object_or_404(Shop, owner=request.user)
        today = timezone.now().date()
        days = int(request.query_params.get('days', 7))
        end_date = today + timedelta(days=days)
        
        bookings = Booking.objects.filter(
            shop=shop,
            slot__start_time__date__gte=today,
            slot__start_time__date__lt=end_date,
            status__in=['active', 'completed']
        ).select_related('user', 'slot__service').order_by('slot__start_time')
        
        # Group by date
        schedule = {}
        for booking in bookings:
            date_key = booking.slot.start_time.date().isoformat()
            if date_key not in schedule:
                schedule[date_key] = []
            schedule[date_key].append({
                'id': booking.id,
                'user_name': booking.user.name,
                'user_email': booking.user.email,
                'service_title': booking.slot.service.title,
                'slot_time': booking.slot.start_time.isoformat(),
                'status': booking.status,
                'prep_notes': booking.prep_notes,
            })
        
        return Response({
            'start_date': today.isoformat(),
            'end_date': end_date.isoformat(),
            'total_appointments': bookings.count(),
            'schedule': schedule
        })


class PrepNotesView(APIView):
    """Get and update prep notes for today's appointments"""
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]
    
    def get(self, request):
        """Get today's appointments with prep notes"""
        shop = get_object_or_404(Shop, owner=request.user)
        today = timezone.now().date()
        
        bookings = Booking.objects.filter(
            shop=shop,
            slot__start_time__date=today,
            status__in=['active']
        ).select_related('user', 'slot__service').order_by('slot__start_time')
        
        serializer = PrepNotesSerializer(bookings, many=True)
        return Response({
            'count': bookings.count(),
            'appointments': serializer.data
        })
    
    def patch(self, request):
        """Update prep notes for a booking"""
        shop = get_object_or_404(Shop, owner=request.user)
        booking_id = request.data.get('booking_id')
        prep_notes = request.data.get('prep_notes', '')
        
        booking = get_object_or_404(Booking, id=booking_id, shop=shop)
        booking.prep_notes = prep_notes
        booking.save()
        
        return Response({
            'id': booking.id,
            'prep_notes': booking.prep_notes
        })


class ClientHairProfileViewSet(viewsets.ModelViewSet):
    """CRUD for client hair profiles"""
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]
    serializer_class = ClientHairProfileSerializer
    
    def get_queryset(self):
        shop = get_object_or_404(Shop, owner=self.request.user)
        return ClientHairProfile.objects.filter(shop=shop).select_related('client')
    
    def perform_create(self, serializer):
        shop = get_object_or_404(Shop, owner=self.request.user)
        serializer.save(shop=shop)


class ProductRecommendationViewSet(viewsets.ModelViewSet):
    """CRUD for product recommendations"""
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]
    serializer_class = ProductRecommendationSerializer
    
    def get_queryset(self):
        shop = get_object_or_404(Shop, owner=self.request.user)
        
        # Optional filters
        client_id = self.request.query_params.get('client')
        category = self.request.query_params.get('category')
        
        qs = ProductRecommendation.objects.filter(shop=shop).select_related('client')
        if client_id:
            qs = qs.filter(client_id=client_id)
        if category:
            qs = qs.filter(category=category)
        return qs
    
    def perform_create(self, serializer):
        shop = get_object_or_404(Shop, owner=self.request.user)
        serializer.save(shop=shop)
