# Makeup Artist Dashboard Views
from django.utils import timezone
from django.db.models import Sum, Q
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.shortcuts import get_object_or_404

from .models import Shop, Service, GalleryItem, ClientBeautyProfile, ProductKitItem
from .permissions import IsOwnerRole, IsOwnerAndOwnerRole
from .mua_serializers import (
    ClientBeautyProfileSerializer, ProductKitItemSerializer,
    FaceChartSerializer, MUADashboardSerializer
)
from payments.models import Booking


class MUADashboardView(APIView):
    """Aggregated dashboard data for MUA niche"""
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]
    
    def get(self, request):
        shop = get_object_or_404(Shop, owner=request.user)
        today = timezone.now().date()
        
        # Today's appointments (reuse logic from barber)
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
        
        # Client profiles count
        client_profiles = ClientBeautyProfile.objects.filter(shop=shop).count()
        
        # Product kit count
        product_kit = ProductKitItem.objects.filter(shop=shop).count()
        
        # Face charts count (GalleryItems with category_tag='face_chart')
        face_charts = GalleryItem.objects.filter(
            shop=shop
        ).filter(
            Q(category_tag__icontains='face_chart') |
            Q(category_tag__icontains='facechart') |
            Q(client__isnull=False)  # Any gallery item linked to client
        ).count()
        
        # Mobile services count
        mobile_services = Service.objects.filter(
            shop=shop,
            is_mobile_service=True,
            is_active=True
        ).count()
        
        return Response({
            'today_appointments_count': today_appointments,
            'today_revenue': float(today_revenue),
            'client_profiles_count': client_profiles,
            'product_kit_count': product_kit,
            'face_charts_count': face_charts,
            'mobile_services_count': mobile_services
        })


class FaceChartListView(APIView):
    """List face charts (filtered GalleryItems with client link)"""
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    def get(self, request):
        shop = get_object_or_404(Shop, owner=request.user)
        
        # Get GalleryItems that are face charts
        face_charts = GalleryItem.objects.filter(
            shop=shop
        ).filter(
            Q(category_tag__icontains='face_chart') |
            Q(category_tag__icontains='facechart') |
            Q(client__isnull=False)
        ).select_related('client').order_by('-created_at')
        
        # Optional look_type filter
        look_type = request.query_params.get('look_type')
        if look_type:
            face_charts = face_charts.filter(look_type=look_type)
        
        serializer = FaceChartSerializer(face_charts, many=True)
        return Response({
            'count': face_charts.count(),
            'items': serializer.data
        })
    
    def post(self, request):
        """Create a new face chart"""
        shop = get_object_or_404(Shop, owner=request.user)
        serializer = FaceChartSerializer(data=request.data)
        
        if serializer.is_valid():
            # Ensure category_tag is set for face charts
            face_chart = serializer.save(
                shop=shop,
                category_tag='face_chart'
            )
            return Response(
                FaceChartSerializer(face_chart).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ClientBeautyProfileViewSet(viewsets.ModelViewSet):
    """CRUD for client beauty profiles"""
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]
    serializer_class = ClientBeautyProfileSerializer
    
    def get_queryset(self):
        shop = get_object_or_404(Shop, owner=self.request.user)
        return ClientBeautyProfile.objects.filter(shop=shop).select_related('client')
    
    def perform_create(self, serializer):
        shop = get_object_or_404(Shop, owner=self.request.user)
        serializer.save(shop=shop)


class ProductKitViewSet(viewsets.ModelViewSet):
    """CRUD for product kit items"""
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]
    serializer_class = ProductKitItemSerializer
    
    def get_queryset(self):
        shop = get_object_or_404(Shop, owner=self.request.user)
        
        # Optional category filter
        category = self.request.query_params.get('category')
        qs = ProductKitItem.objects.filter(shop=shop)
        if category:
            qs = qs.filter(category=category)
        return qs
    
    def perform_create(self, serializer):
        shop = get_object_or_404(Shop, owner=self.request.user)
        serializer.save(shop=shop)
    
    def toggle_packed(self, request, pk=None):
        """Toggle is_packed status"""
        item = self.get_object()
        item.is_packed = not item.is_packed
        item.save()
        return Response({'is_packed': item.is_packed})
