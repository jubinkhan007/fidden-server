# Hairstylist/Loctician Dashboard Views
from datetime import timedelta
from django.utils import timezone
from django.db.models import Sum, Q
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from .models import Shop, Service, ServiceCategory, ClientHairProfile, ProductRecommendation
from .permissions import IsOwnerAndOwnerRole
from .hairstylist_serializers import (
    ClientHairProfileSerializer, ProductRecommendationSerializer,
    PrepNotesSerializer, HairstylistDashboardSerializer
)
from payments.models import Booking

# Define hair-related category names for filtering
HAIR_CATEGORY_KEYWORDS = ['hair', 'haircut', 'hairstyle', 'locs', 'braids', 'weave']


class HairstylistDashboardView(APIView):
    """Aggregated dashboard data for Hairstylist niche"""
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]
    
    def get(self, request):
        import pytz
        shop = get_object_or_404(Shop, owner=request.user)
        
        # Use shop's timezone for "today" calculation
        shop_tz = pytz.timezone(shop.time_zone) if shop.time_zone else pytz.UTC
        now_local = timezone.now().astimezone(shop_tz)
        today = now_local.date()
        week_end = today + timedelta(days=7)
        
        # Get hair-related categories
        hair_category_q = Q()
        for keyword in HAIR_CATEGORY_KEYWORDS:
            hair_category_q |= Q(name__icontains=keyword)
        hair_category_ids = ServiceCategory.objects.filter(hair_category_q).values_list('id', flat=True)
        
        # Base filter for hair services
        hair_service_filter = Q(slot__service__category_id__in=hair_category_ids)
        
        # Create timezone-aware datetime range for today
        today_start = shop_tz.localize(timezone.datetime(today.year, today.month, today.day, 0, 0, 0))
        today_end = today_start + timedelta(days=1)
        week_end_dt = today_start + timedelta(days=7)
        
        # Today's appointments (hair services only) - use datetime range for timezone accuracy
        today_appointments = Booking.objects.filter(
            hair_service_filter,
            shop=shop,
            slot__start_time__gte=today_start,
            slot__start_time__lt=today_end,
            status__in=['active', 'completed']
        ).count()
        
        # Week appointments (next 7 days, hair services only)
        week_appointments = Booking.objects.filter(
            hair_service_filter,
            shop=shop,
            slot__start_time__gte=today_start,
            slot__start_time__lt=week_end_dt,
            status__in=['active', 'completed']
        ).count()
        
        # Today's revenue - calculate from actual payments for hair services
        from payments.models import Payment
        from django.db.models.functions import Coalesce
        from django.db.models import DecimalField, Value
        from decimal import Decimal
        
        # Get today's hair service bookings (use same datetime range as appointments)
        today_hair_bookings = Booking.objects.filter(
            hair_service_filter,
            shop=shop,
            slot__start_time__gte=today_start,
            slot__start_time__lt=today_end,
            status__in=['active', 'completed']
        )
        
        # Get slot_ids (Payment.booking_id references SlotBooking.id)
        slot_ids = list(today_hair_bookings.values_list('slot_id', flat=True))
        
        # Sum payments for these hair service bookings
        today_revenue = Payment.objects.filter(
            booking_id__in=slot_ids,
            status='succeeded'
        ).aggregate(
            total=Coalesce(Sum('amount'), Value(Decimal('0')), output_field=DecimalField())
        )['total'] or 0
        
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
        
        # Get hair-related categories
        hair_category_q = Q()
        for keyword in HAIR_CATEGORY_KEYWORDS:
            hair_category_q |= Q(name__icontains=keyword)
        hair_category_ids = ServiceCategory.objects.filter(hair_category_q).values_list('id', flat=True)
        
        bookings = Booking.objects.filter(
            shop=shop,
            slot__start_time__date__gte=today,
            slot__start_time__date__lt=end_date,
            slot__service__category_id__in=hair_category_ids,
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
        
        # Get hair-related categories
        hair_category_q = Q()
        for keyword in HAIR_CATEGORY_KEYWORDS:
            hair_category_q |= Q(name__icontains=keyword)
        hair_category_ids = ServiceCategory.objects.filter(hair_category_q).values_list('id', flat=True)
        
        bookings = Booking.objects.filter(
            shop=shop,
            slot__start_time__date=today,
            slot__service__category_id__in=hair_category_ids,
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
    """
    CRUD for client hair profiles - OWNER ONLY.
    Owner can view/create/edit profiles for any client in their shop.
    """
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]
    serializer_class = ClientHairProfileSerializer
    
    def get_queryset(self):
        shop = get_object_or_404(Shop, owner=self.request.user)
        return ClientHairProfile.objects.filter(shop=shop).select_related('client')
    
    def create(self, request, *args, **kwargs):
        """Override to check for existing profile before creating"""
        shop = get_object_or_404(Shop, owner=request.user)
        client_id = request.data.get('client')
        
        if client_id and ClientHairProfile.objects.filter(shop=shop, client_id=client_id).exists():
            return Response(
                {'error': 'Profile already exists for this client. Use PATCH to update.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return super().create(request, *args, **kwargs)
    
    def perform_create(self, serializer):
        shop = get_object_or_404(Shop, owner=self.request.user)
        serializer.save(shop=shop)


class MyHairProfileView(APIView):
    """
    Client's own hair profile - self-service.
    Clients can view/create/edit their OWN profile for a specific shop.
    
    Query param: ?shop_id=5
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get client's own hair profile for a shop"""
        shop_id = request.query_params.get('shop_id')
        if not shop_id:
            return Response({'error': 'shop_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        shop = get_object_or_404(Shop, id=shop_id)
        profile = ClientHairProfile.objects.filter(shop=shop, client=request.user).first()
        
        if not profile:
            return Response({'exists': False, 'profile': None})
        
        serializer = ClientHairProfileSerializer(profile)
        return Response({'exists': True, 'profile': serializer.data})
    
    def post(self, request):
        """Create client's own hair profile"""
        shop_id = request.data.get('shop_id')
        if not shop_id:
            return Response({'error': 'shop_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        shop = get_object_or_404(Shop, id=shop_id)
        
        # Check if profile already exists
        if ClientHairProfile.objects.filter(shop=shop, client=request.user).exists():
            return Response({'error': 'Profile already exists. Use PATCH to update.'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        serializer = ClientHairProfileSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(shop=shop, client=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def patch(self, request):
        """Update client's own hair profile"""
        shop_id = request.data.get('shop_id')
        if not shop_id:
            return Response({'error': 'shop_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        shop = get_object_or_404(Shop, id=shop_id)
        profile = get_object_or_404(ClientHairProfile, shop=shop, client=request.user)
        
        serializer = ClientHairProfileSerializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
