# Esthetician/Massage Therapist Dashboard Views
from datetime import timedelta
from django.utils import timezone
from django.db.models import Sum
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from .models import (
    Shop, Service, ClientSkinProfile, HealthDisclosure,
    TreatmentNote, RetailProduct, Revenue
)
from .permissions import IsOwnerAndOwnerRole
from .esthetician_serializers import (
    ClientSkinProfileSerializer, HealthDisclosureSerializer,
    TreatmentNoteSerializer, RetailProductSerializer
)
from payments.models import Booking


class EstheticianDashboardView(APIView):
    """Aggregated dashboard data for Esthetician/Massage niche"""
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
        
        # Week appointments
        week_appointments = Booking.objects.filter(
            shop=shop,
            slot__start_time__date__gte=today,
            slot__start_time__date__lt=week_end,
            status__in=['active', 'completed']
        ).count()
        
        # Today's revenue
        today_revenue = Revenue.objects.filter(
            shop=shop,
            timestamp=today
        ).aggregate(total=Sum('revenue'))['total'] or 0
        
        # Client profiles count
        client_profiles = ClientSkinProfile.objects.filter(shop=shop).count()
        
        # Retail products count
        retail_products = RetailProduct.objects.filter(shop=shop, is_active=True).count()
        
        # Disclosure alerts - clients with health conditions for today's appointments
        today_bookings = Booking.objects.filter(
            shop=shop,
            slot__start_time__date=today,
            status='active'
        ).select_related('user')
        
        disclosure_alerts = []
        for booking in today_bookings:
            disclosure = HealthDisclosure.objects.filter(
                shop=shop,
                client=booking.user,
                has_medical_conditions=True
            ).order_by('-created_at').first()
            if disclosure:
                disclosure_alerts.append({
                    'client_name': booking.user.name,
                    'client_id': booking.user.id,
                    'booking_id': booking.id,
                    'has_conditions': True,
                    'pregnant_or_nursing': disclosure.pregnant_or_nursing,
                })
        
        # Recent treatment notes (last 5)
        recent_notes = TreatmentNote.objects.filter(shop=shop)[:5]
        recent_treatment_notes = [
            {
                'id': note.id,
                'client_name': note.client.name,
                'treatment_type': note.treatment_type,
                'treatment_type_display': note.get_treatment_type_display(),
                'created_at': note.created_at.isoformat(),
            }
            for note in recent_notes
        ]
        
        return Response({
            'today_appointments_count': today_appointments,
            'week_appointments_count': week_appointments,
            'today_revenue': float(today_revenue),
            'client_profiles_count': client_profiles,
            'retail_products_count': retail_products,
            'disclosure_alerts': disclosure_alerts,
            'recent_treatment_notes': recent_treatment_notes,
        })


class ClientSkinProfileViewSet(viewsets.ModelViewSet):
    """CRUD for client skin profiles - OWNER ONLY"""
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]
    serializer_class = ClientSkinProfileSerializer
    
    def get_queryset(self):
        shop = get_object_or_404(Shop, owner=self.request.user)
        return ClientSkinProfile.objects.filter(shop=shop).select_related('client')
    
    def perform_create(self, serializer):
        shop = get_object_or_404(Shop, owner=self.request.user)
        serializer.save(shop=shop)


class MySkinProfileView(APIView):
    """Client's own skin profile - self-service"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        shop_id = request.query_params.get('shop_id')
        if not shop_id:
            return Response({'error': 'shop_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        shop = get_object_or_404(Shop, id=shop_id)
        profile = ClientSkinProfile.objects.filter(shop=shop, client=request.user).first()
        
        if not profile:
            return Response({'exists': False, 'profile': None})
        
        serializer = ClientSkinProfileSerializer(profile)
        return Response({'exists': True, 'profile': serializer.data})
    
    def post(self, request):
        shop_id = request.data.get('shop_id')
        if not shop_id:
            return Response({'error': 'shop_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        shop = get_object_or_404(Shop, id=shop_id)
        
        if ClientSkinProfile.objects.filter(shop=shop, client=request.user).exists():
            return Response({'error': 'Profile already exists. Use PATCH to update.'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        serializer = ClientSkinProfileSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(shop=shop, client=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def patch(self, request):
        shop_id = request.data.get('shop_id')
        if not shop_id:
            return Response({'error': 'shop_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        shop = get_object_or_404(Shop, id=shop_id)
        profile = get_object_or_404(ClientSkinProfile, shop=shop, client=request.user)
        
        serializer = ClientSkinProfileSerializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class HealthDisclosureViewSet(viewsets.ModelViewSet):
    """CRUD for health disclosures - OWNER ONLY"""
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]
    serializer_class = HealthDisclosureSerializer
    
    def get_queryset(self):
        shop = get_object_or_404(Shop, owner=self.request.user)
        client_id = self.request.query_params.get('client')
        qs = HealthDisclosure.objects.filter(shop=shop).select_related('client')
        if client_id:
            qs = qs.filter(client_id=client_id)
        return qs
    
    def perform_create(self, serializer):
        shop = get_object_or_404(Shop, owner=self.request.user)
        serializer.save(shop=shop, created_by=self.request.user)


class MyHealthDisclosureView(APIView):
    """Client's own health disclosure - self-service"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        shop_id = request.query_params.get('shop_id')
        if not shop_id:
            return Response({'error': 'shop_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        shop = get_object_or_404(Shop, id=shop_id)
        # Get latest disclosure for this client at this shop
        disclosure = HealthDisclosure.objects.filter(
            shop=shop, client=request.user
        ).order_by('-created_at').first()
        
        if not disclosure:
            return Response({'exists': False, 'disclosure': None})
        
        serializer = HealthDisclosureSerializer(disclosure)
        return Response({'exists': True, 'disclosure': serializer.data})
    
    def post(self, request):
        shop_id = request.data.get('shop_id')
        if not shop_id:
            return Response({'error': 'shop_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        shop = get_object_or_404(Shop, id=shop_id)
        
        serializer = HealthDisclosureSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(shop=shop, client=request.user, created_by=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def patch(self, request):
        shop_id = request.data.get('shop_id')
        if not shop_id:
            return Response({'error': 'shop_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        shop = get_object_or_404(Shop, id=shop_id)
        disclosure = HealthDisclosure.objects.filter(
            shop=shop, client=request.user
        ).order_by('-created_at').first()
        
        if not disclosure:
            return Response({'error': 'No disclosure found'}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = HealthDisclosureSerializer(disclosure, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TreatmentNoteViewSet(viewsets.ModelViewSet):
    """CRUD for treatment notes - OWNER ONLY"""
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]
    serializer_class = TreatmentNoteSerializer
    
    def get_queryset(self):
        shop = get_object_or_404(Shop, owner=self.request.user)
        client_id = self.request.query_params.get('client')
        booking_id = self.request.query_params.get('booking')
        
        qs = TreatmentNote.objects.filter(shop=shop).select_related('client', 'booking')
        if client_id:
            qs = qs.filter(client_id=client_id)
        if booking_id:
            qs = qs.filter(booking_id=booking_id)
        return qs
    
    def perform_create(self, serializer):
        shop = get_object_or_404(Shop, owner=self.request.user)
        serializer.save(shop=shop)


class RetailProductViewSet(viewsets.ModelViewSet):
    """CRUD for retail products - OWNER ONLY"""
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]
    serializer_class = RetailProductSerializer
    
    def get_queryset(self):
        shop = get_object_or_404(Shop, owner=self.request.user)
        category = self.request.query_params.get('category')
        in_stock = self.request.query_params.get('in_stock')
        
        qs = RetailProduct.objects.filter(shop=shop)
        if category:
            qs = qs.filter(category=category)
        if in_stock is not None:
            qs = qs.filter(in_stock=in_stock.lower() == 'true')
        return qs
    
    def perform_create(self, serializer):
        shop = get_object_or_404(Shop, owner=self.request.user)
        serializer.save(shop=shop)
