from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Sum
from django.utils import timezone
from datetime import timedelta

from .models import Shop, FitnessPackage, WorkoutTemplate, NutritionPlan, Revenue
from .permissions import IsOwnerAndOwnerRole
from .fitness_serializers import (
    FitnessPackageSerializer, 
    WorkoutTemplateSerializer, 
    NutritionPlanSerializer
)
from payments.models import Booking

class FitnessTrainerDashboardView(APIView):
    """
    Aggregated stats for the Fitness Trainer Dashboard (Phase 2A MVP).
    """
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]

    def get(self, request):
        shop = get_object_or_404(Shop, owner=request.user)
        today = timezone.now().date()
        week_start = today
        week_end = today + timedelta(days=7)

        # 1. Weekly Schedule Counts (class vs 1to1)
        bookings = Booking.objects.filter(
            shop=shop,
            slot__start_time__date__gte=week_start,
            slot__start_time__date__lte=week_end
        ).select_related('slot__service')

        class_count = 0
        one_to_one_count = 0
        for b in bookings:
            if b.slot and b.slot.service and (b.slot.service.capacity or 1) > 1:
                class_count += 1
            else:
                one_to_one_count += 1

        # 2. Revenue Totals (From Revenue model snapshot)
        revenue_stats = Revenue.objects.filter(shop=shop).aggregate(
            total=Sum('revenue')
        )
        paid_total = revenue_stats['total'] or 0

        # 3. Booking Stats
        pending_deposit_count = Booking.objects.filter(
            shop=shop,
            payment__is_deposit=True,
            payment__deposit_status='pending'
        ).count()

        active_packages_count = FitnessPackage.objects.filter(
            shop=shop,
            is_active=True,
            sessions_remaining__gt=0
        ).count()

        return Response({
            "weekly_schedule": {
                "classes": class_count,
                "one_to_one": one_to_one_count,
                "total": bookings.count()
            },
            "revenue": {
                "paid_total": float(paid_total),
                "pending_deposit_count": pending_deposit_count
            },
            "packages": {
                "active_count": active_packages_count
            },
            "shop_settings": {
                "cancellation_policy_enabled": shop.cancellation_policy_enabled,
                "free_cancellation_hours": shop.free_cancellation_hours
            }
        })

class FitnessPackageViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]
    serializer_class = FitnessPackageSerializer

    def get_queryset(self):
        shop = get_object_or_404(Shop, owner=self.request.user)
        return FitnessPackage.objects.filter(shop=shop)

    def perform_create(self, serializer):
        shop = get_object_or_404(Shop, owner=self.request.user)
        serializer.save(shop=shop)

class WorkoutTemplateViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]
    serializer_class = WorkoutTemplateSerializer

    def get_queryset(self):
        shop = get_object_or_404(Shop, owner=self.request.user)
        return WorkoutTemplate.objects.filter(shop=shop)

    def perform_create(self, serializer):
        shop = get_object_or_404(Shop, owner=self.request.user)
        serializer.save(shop=shop)

class NutritionPlanViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]
    serializer_class = NutritionPlanSerializer

    def get_queryset(self):
        shop = get_object_or_404(Shop, owner=self.request.user)
        return NutritionPlan.objects.filter(shop=shop)

    def perform_create(self, serializer):
        shop = get_object_or_404(Shop, owner=self.request.user)
        serializer.save(shop=shop)
