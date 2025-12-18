# Massage Therapist Dashboard Views
from datetime import timedelta
from django.utils import timezone
from django.db.models import Sum
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from .models import (
    Shop, ClientMassageProfile, SessionNote,
    HealthDisclosure, Revenue
)
from .permissions import IsOwnerAndOwnerRole
from .massage_serializers import (
    ClientMassageProfileSerializer, SessionNoteSerializer,
    MassageHealthDisclosureSerializer
)
from payments.models import Booking


class MassageDashboardView(APIView):
    """Aggregated dashboard data for Massage Therapist niche"""
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
        client_profiles = ClientMassageProfile.objects.filter(shop=shop).count()
        
        # Disclosure alerts - clients with health conditions for today
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
                    'areas_to_avoid': disclosure.areas_to_avoid,
                })
        
        # Recent session notes (last 5)
        recent_notes = SessionNote.objects.filter(shop=shop)[:5]
        recent_session_notes = [
            {
                'id': note.id,
                'client_name': note.client.name,
                'technique_used': note.technique_used,
                'technique_display': note.get_technique_used_display(),
                'created_at': note.created_at.isoformat(),
            }
            for note in recent_notes
        ]
        
        return Response({
            'today_appointments_count': today_appointments,
            'week_appointments_count': week_appointments,
            'today_revenue': float(today_revenue),
            'client_profiles_count': client_profiles,
            'disclosure_alerts': disclosure_alerts,
            'recent_session_notes': recent_session_notes,
        })


class ClientMassageProfileViewSet(viewsets.ModelViewSet):
    """CRUD for client massage profiles - OWNER ONLY"""
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]
    serializer_class = ClientMassageProfileSerializer
    
    def get_queryset(self):
        shop = get_object_or_404(Shop, owner=self.request.user)
        return ClientMassageProfile.objects.filter(shop=shop).select_related('client')
    
    def perform_create(self, serializer):
        shop = get_object_or_404(Shop, owner=self.request.user)
        serializer.save(shop=shop)


class MyMassageProfileView(APIView):
    """Client's own massage profile - self-service"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        shop_id = request.query_params.get('shop_id')
        if not shop_id:
            return Response({'error': 'shop_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        shop = get_object_or_404(Shop, id=shop_id)
        profile = ClientMassageProfile.objects.filter(shop=shop, client=request.user).first()
        
        if not profile:
            return Response({'exists': False, 'profile': None})
        
        serializer = ClientMassageProfileSerializer(profile)
        return Response({'exists': True, 'profile': serializer.data})
    
    def post(self, request):
        shop_id = request.data.get('shop_id')
        if not shop_id:
            return Response({'error': 'shop_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        shop = get_object_or_404(Shop, id=shop_id)
        
        if ClientMassageProfile.objects.filter(shop=shop, client=request.user).exists():
            return Response({'error': 'Profile already exists. Use PATCH to update.'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        serializer = ClientMassageProfileSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(shop=shop, client=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def patch(self, request):
        shop_id = request.data.get('shop_id')
        if not shop_id:
            return Response({'error': 'shop_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        shop = get_object_or_404(Shop, id=shop_id)
        profile = get_object_or_404(ClientMassageProfile, shop=shop, client=request.user)
        
        serializer = ClientMassageProfileSerializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MassageHealthDisclosureViewSet(viewsets.ModelViewSet):
    """CRUD for health disclosures (massage-focused) - OWNER ONLY"""
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]
    serializer_class = MassageHealthDisclosureSerializer
    
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


class SessionNoteViewSet(viewsets.ModelViewSet):
    """CRUD for session notes - OWNER ONLY"""
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]
    serializer_class = SessionNoteSerializer
    
    def get_queryset(self):
        shop = get_object_or_404(Shop, owner=self.request.user)
        client_id = self.request.query_params.get('client')
        booking_id = self.request.query_params.get('booking')
        
        qs = SessionNote.objects.filter(shop=shop).select_related('client', 'booking')
        if client_id:
            qs = qs.filter(client_id=client_id)
        if booking_id:
            qs = qs.filter(booking_id=booking_id)
        return qs
    
    def perform_create(self, serializer):
        shop = get_object_or_404(Shop, owner=self.request.user)
        serializer.save(shop=shop)
