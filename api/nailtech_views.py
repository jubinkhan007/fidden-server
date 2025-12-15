# Nail Tech Dashboard Views
from django.utils import timezone
from django.db.models import Sum, Count, Avg, Q
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.shortcuts import get_object_or_404

from .models import Shop, Service, StyleRequest, StyleRequestImage, GalleryItem, PerformanceAnalytics
from .permissions import IsOwnerRole, IsOwnerAndOwnerRole
from .nailtech_serializers import (
    StyleRequestSerializer, StyleRequestImageSerializer,
    LookbookItemSerializer, BookingByStyleSerializer,
    TipSummarySerializer, NailTechDashboardSerializer
)
from payments.models import Booking, Payment


class StyleRequestViewSet(viewsets.ModelViewSet):
    """CRUD for nail style requests"""
    permission_classes = [IsAuthenticated]
    serializer_class = StyleRequestSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    def get_queryset(self):
        user = self.request.user
        if user.role == 'owner':
            shop = get_object_or_404(Shop, owner=user)
            return StyleRequest.objects.filter(shop=shop).select_related('user').prefetch_related('images')
        else:
            return StyleRequest.objects.filter(user=user).prefetch_related('images')
    
    def perform_create(self, serializer):
        # Client creates style request for a shop
        shop_id = self.request.data.get('shop')
        shop = get_object_or_404(Shop, id=shop_id)
        style_request = serializer.save(shop=shop, user=self.request.user)
        
        # Handle image uploads
        images = self.request.FILES.getlist('images')
        for image in images:
            StyleRequestImage.objects.create(style_request=style_request, image=image)
    
    def partial_update(self, request, *args, **kwargs):
        """Update style request status (owner only)"""
        instance = self.get_object()
        if request.user.role == 'owner':
            shop = get_object_or_404(Shop, owner=request.user)
            if instance.shop != shop:
                return Response({'error': 'Not your shop'}, status=status.HTTP_403_FORBIDDEN)
        
        return super().partial_update(request, *args, **kwargs)


class LookbookView(APIView):
    """Get nail lookbook/moodboard items (filtered GalleryItems)"""
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]
    
    def get(self, request):
        shop = get_object_or_404(Shop, owner=request.user)
        
        # Get GalleryItems that are nail-related
        lookbook = GalleryItem.objects.filter(
            shop=shop
        ).filter(
            Q(category_tag__icontains='nail') |
            Q(category_tag__icontains='lookbook') |
            Q(category_tag__icontains='moodboard') |
            Q(category_tag='')  # Include uncategorized for now
        ).order_by('-created_at')
        
        serializer = LookbookItemSerializer(lookbook, many=True)
        return Response({
            'count': lookbook.count(),
            'items': serializer.data
        })


class BookingsByStyleView(APIView):
    """Get bookings grouped by nail style type"""
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]
    
    def get(self, request):
        shop = get_object_or_404(Shop, owner=request.user)
        
        # Get date range from query params (default: last 30 days)
        days = int(request.query_params.get('days', 30))
        cutoff_date = timezone.now() - timezone.timedelta(days=days)
        
        # Get bookings with nail style services
        bookings = Booking.objects.filter(
            shop=shop,
            slot__start_time__gte=cutoff_date,
            status__in=['active', 'completed']
        ).select_related('slot__service')
        
        # Group by service nail_style_type
        style_counts = {}
        for booking in bookings:
            service = booking.slot.service if booking.slot else None
            if service and service.nail_style_type:
                style_type = service.nail_style_type
                if style_type not in style_counts:
                    style_counts[style_type] = {
                        'count': 0,
                        'revenue': 0,
                        'display': service.get_nail_style_type_display()
                    }
                style_counts[style_type]['count'] += 1
                style_counts[style_type]['revenue'] += float(service.price)
        
        # Format response
        results = [
            {
                'style_type': style,
                'style_display': data['display'],
                'count': data['count'],
                'revenue': data['revenue']
            }
            for style, data in style_counts.items()
        ]
        
        return Response({
            'period_days': days,
            'styles': sorted(results, key=lambda x: x['count'], reverse=True)
        })


class TipSummaryView(APIView):
    """Get tip summary for nail tech"""
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]
    
    def get(self, request):
        shop = get_object_or_404(Shop, owner=request.user)
        
        # Get period from query params (day, week, month)
        period = request.query_params.get('period', 'week')
        
        if period == 'day':
            cutoff = timezone.now() - timezone.timedelta(days=1)
        elif period == 'month':
            cutoff = timezone.now() - timezone.timedelta(days=30)
        else:  # week
            cutoff = timezone.now() - timezone.timedelta(days=7)
        
        # Aggregate tips
        tips = Payment.objects.filter(
            booking__shop=shop,
            created_at__gte=cutoff,
            tip__gt=0
        ).aggregate(
            total=Sum('tip'),
            count=Count('id'),
            average=Avg('tip')
        )
        
        return Response({
            'period': period,
            'total_tips': float(tips['total'] or 0),
            'tip_count': tips['count'] or 0,
            'average_tip': float(tips['average'] or 0)
        })


class NailTechDashboardView(APIView):
    """Aggregated dashboard data for Nail Tech niche"""
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]
    
    def get(self, request):
        shop = get_object_or_404(Shop, owner=request.user)
        today = timezone.now().date()
        week_ago = timezone.now() - timezone.timedelta(days=7)
        
        # Today's appointments
        today_appointments = Booking.objects.filter(
            shop=shop,
            slot__start_time__date=today,
            status__in=['active', 'completed']
        ).count()
        
        # Today's revenue
        from .models import Revenue
        today_revenue = Revenue.objects.filter(
            shop=shop,
            timestamp=today
        ).aggregate(total=Sum('revenue'))['total'] or 0
        
        # Pending style requests
        pending_requests = StyleRequest.objects.filter(
            shop=shop,
            status='pending'
        ).count()
        
        # Repeat customer rate from PerformanceAnalytics
        try:
            analytics = shop.analytics
            repeat_rate = analytics.repeat_customer_rate
        except PerformanceAnalytics.DoesNotExist:
            repeat_rate = 0.0
        
        # Weekly tips
        weekly_tips = Payment.objects.filter(
            booking__shop=shop,
            created_at__gte=week_ago,
            tip__gt=0
        ).aggregate(total=Sum('tip'))['total'] or 0
        
        # Lookbook count
        lookbook_count = GalleryItem.objects.filter(shop=shop).count()
        
        return Response({
            'today_appointments_count': today_appointments,
            'today_revenue': float(today_revenue),
            'pending_style_requests': pending_requests,
            'repeat_customer_rate': repeat_rate,
            'weekly_tips': float(weekly_tips),
            'lookbook_count': lookbook_count
        })
