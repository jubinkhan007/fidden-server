# api/walk_in_views.py
"""
Walk-In Queue API endpoints.
Allows shop owners to manage walk-in customers and integrate with existing checkout flow.
"""
from decimal import Decimal
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db import transaction

from .models import WalkInEntry, SlotBooking, Slot, Service
from .walk_in_serializers import (
    WalkInEntrySerializer,
    WalkInCheckoutSerializer,
    WalkInStatsSerializer
)
from .permissions import IsOwnerAndOwnerRole
from payments.models import Payment, TransactionLog


class WalkInViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing walk-in queue entries.
    
    Endpoints:
        GET    /api/walk-in/              - List today's queue
        POST   /api/walk-in/              - Add customer to queue
        PATCH  /api/walk-in/{id}/         - Update entry (status, etc.)
        DELETE /api/walk-in/{id}/         - Remove from queue
        POST   /api/walk-in/{id}/start/   - Mark as in_service
        POST   /api/walk-in/{id}/complete/- Complete with payment
        POST   /api/walk-in/{id}/no_show/ - Mark as no_show
        GET    /api/walk-in/stats/        - Get queue stats
    """
    
    serializer_class = WalkInEntrySerializer
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]
    
    def get_queryset(self):
        """Get today's walk-in entries for the shop."""
        shop = self.request.user.shop
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        queryset = WalkInEntry.objects.filter(
            shop=shop,
            joined_at__gte=today_start
        )
        
        # Optional filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Optional filter by niche
        niche = self.request.query_params.get('service_niche')
        if niche:
            queryset = queryset.filter(service_niche=niche)
        
        return queryset.order_by('position')
    
    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """Mark walk-in as in_service (started serving)."""
        entry = self.get_object()
        
        if entry.status != 'waiting':
            return Response(
                {'error': f'Cannot start service. Current status: {entry.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        entry.status = 'in_service'
        entry.called_at = timezone.now()
        entry.save()
        
        serializer = self.get_serializer(entry)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def no_show(self, request, pk=None):
        """Mark walk-in as no_show."""
        entry = self.get_object()
        
        if entry.status not in ['waiting', 'in_service']:
            return Response(
                {'error': f'Cannot mark as no-show. Current status: {entry.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        entry.status = 'no_show'
        entry.save()
        
        serializer = self.get_serializer(entry)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """
        Complete walk-in with payment.
        Creates SlotBooking, Payment, and TransactionLog records.
        """
        entry = self.get_object()
        
        if entry.status not in ['waiting', 'in_service']:
            return Response(
                {'error': f'Cannot complete. Current status: {entry.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        checkout_serializer = WalkInCheckoutSerializer(data=request.data)
        if not checkout_serializer.is_valid():
            return Response(checkout_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        payment_data = checkout_serializer.validated_data
        
        with transaction.atomic():
            # 1. Update walk-in entry
            entry.status = 'completed'
            entry.completed_at = timezone.now()
            entry.amount_paid = payment_data['amount_paid']
            entry.tips_amount = payment_data.get('tips_amount', Decimal('0'))
            entry.payment_method = payment_data['payment_method']
            
            # 2. Create or get a slot for the walk-in
            slot = self._get_or_create_walk_in_slot(entry)
            
            # 3. Create SlotBooking record
            slot_booking = SlotBooking.objects.create(
                user=entry.user,  # May be None for walk-ins without account
                shop=entry.shop,
                service=entry.service,
                slot=slot,
                start_time=entry.called_at or entry.joined_at,
                end_time=entry.completed_at,
                status='confirmed',
                payment_status='success',
                is_walk_in=True,
                walk_in_customer_name=entry.customer_name,
                walk_in_customer_phone=entry.customer_phone
            )
            
            entry.slot_booking = slot_booking
            entry.save()
            
            # 4. Create Payment record
            total_amount = entry.amount_paid + entry.tips_amount
            payment = Payment.objects.create(
                booking=slot_booking,
                user=entry.user,  # May be None
                amount=total_amount,
                is_deposit=False,
                remaining_amount=Decimal('0'),
                balance_paid=entry.amount_paid,
                deposit_paid=Decimal('0'),
                tips_amount=entry.tips_amount,
                status='succeeded',
                payment_method=entry.payment_method
            )
            
            # 5. Create TransactionLog entry
            TransactionLog.objects.create(
                transaction_type='payment',
                payment=payment,
                user=entry.user,  # May be None
                shop=entry.shop,
                slot=slot_booking,
                service=entry.service,
                amount=total_amount,
                status='succeeded',
                currency='usd'
            )
            
            # 6. Update Revenue
            self._update_revenue(entry.shop, total_amount)
        
        serializer = self.get_serializer(entry)
        return Response(serializer.data)
    
    def _get_or_create_walk_in_slot(self, entry):
        """Get or create a slot for walk-in booking."""
        now = timezone.now()
        
        # Create a walk-in specific slot
        # For walk-ins, we create a slot effectively "on demand"
        slot, created = Slot.objects.get_or_create(
            shop=entry.shop,
            service=entry.service,
            start_time=now.replace(second=0, microsecond=0),
            defaults={
                'capacity_left': 0,  # Immediately consumed
                'end_time': now + timezone.timedelta(minutes=entry.service.duration or 30)
            }
        )
        
        # If slot existed, we don't strictly need to do anything for walk-ins
        # as we are bypassing standard capacity checks
        
        return slot
    
    def _update_revenue(self, shop, amount):
        """Update daily revenue for the shop."""
        from .models import Revenue
        today = timezone.now().date()
        
        revenue, created = Revenue.objects.get_or_create(
            shop=shop,
            timestamp=today,
            defaults={'revenue': Decimal('0')}
        )
        revenue.revenue += amount
        revenue.save()
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get walk-in queue statistics for today."""
        shop = request.user.shop
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        entries = WalkInEntry.objects.filter(
            shop=shop,
            joined_at__gte=today_start
        )
        
        # Optional filter by niche
        niche = request.query_params.get('service_niche')
        if niche:
            entries = entries.filter(service_niche=niche)
        
        stats_data = {
            'waiting': entries.filter(status='waiting').count(),
            'in_service': entries.filter(status='in_service').count(),
            'completed': entries.filter(status='completed').count(),
            'no_show': entries.filter(status='no_show').count(),
            'total': entries.count(),
        }
        
        return Response(stats_data)
