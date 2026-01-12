import logging
from datetime import datetime, date, timedelta
import pytz

from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from api.models import Shop, Service, Provider, ProviderDayLock
from api.utils.availability import (
    provider_available_starts, 
    get_any_provider_availability,
    select_best_provider
)

logger = logging.getLogger(__name__)

class AvailabilityView(APIView):
    """
    Returns available start times for a service on a specific date.
    Query Params:
    - shop_id (required)
    - service_id (required)
    - date (required, YYYY-MM-DD)
    - provider_id (optional)
    """
    authentication_classes = [] # Publicly reachable for booking discovery if needed, or depends on project policy
    permission_classes = []

    def get(self, request):
        shop_id = request.query_params.get('shop_id')
        service_id = request.query_params.get('service_id')
        date_str = request.query_params.get('date')
        provider_id = request.query_params.get('provider_id')

        if not all([shop_id, service_id, date_str]):
            return Response(
                {"detail": "Missing required parameters: shop_id, service_id, date"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            shop = Shop.objects.get(id=shop_id)
            service = Service.objects.get(id=service_id, shop=shop)
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except Shop.DoesNotExist:
            return Response({"detail": "Shop not found"}, status=status.HTTP_404_NOT_FOUND)
        except Service.DoesNotExist:
            return Response({"detail": "Service not found or dose not belong to shop"}, status=status.HTTP_404_NOT_FOUND)
        except ValueError:
            return Response({"detail": "Invalid date format. Use YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST)

        if provider_id:
            try:
                provider = Provider.objects.get(id=provider_id, shop=shop)
                available_times = provider_available_starts(provider, service, target_date)
            except Provider.DoesNotExist:
                return Response({"detail": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)
        else:
            # Aggregate across all providers
            available_times = get_any_provider_availability(shop, service, target_date)

        # Convert datetimes to ISO strings or HH:MM? 
        # Requirement usually expects start times. Let's return local time HH:MM for grid.
        # But we should also provide full ISO for precise POSTing.
        
        # We assume available_times are aware datetimes in target TZ or UTC.
        # The engine returns them in local timezone of shop/provider.
        
        if provider_id:
            available_times = [dt.strftime("%H:%M") for dt in available_times]
        else:
            # list of dicts: {"start_time": dt, "available_count": int}
            available_times = [
                {
                    "time": item["start_time"].strftime("%H:%M"),
                    "count": item["available_count"]
                } for item in available_times
            ]
        
        return Response({
            "date": date_str,
            "shop_id": int(shop_id),
            "service_id": int(service_id),
            "available_starts": available_times
        })


class ProvidersView(APIView):
    """
    List providers for a specific shop and service.
    """
    def get(self, request, shop_id):
        service_id = request.query_params.get('service_id')
        
        qs = Provider.objects.filter(shop_id=shop_id, is_active=True)
        if service_id:
            # Assuming providers might be linked to services via M2M or just all?
            # For now, return all active providers of the shop.
            # In some systems providers might only do certain services.
            pass
            
        data = [{
            "id": p.id,
            "name": p.name,
            "profile_image": p.profile_image.url if p.profile_image else None
        } for p in qs]
        
        return Response(data)

class BookingCreateView(APIView):
    """
    Creates a booking using the multi-provider rule-based engine.
    Instead of locking a Slot row, it locks the ProviderDayLock row for the target date.
    
    Expected Body:
    {
        "shop_id": int,
        "service_id": int,
        "provider_id": int (optional, if null machine will assign),
        "start_at": "ISO 8601 string",
        "coupon_id": int (optional)
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        shop_id = request.data.get('shop_id')
        service_id = request.data.get('service_id')
        provider_id = request.data.get('provider_id')
        start_at_str = request.data.get('start_at')
        
        if not all([shop_id, service_id, start_at_str]):
            return Response({"detail": "Missing shop_id, service_id, or start_at"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start_at = datetime.fromisoformat(start_at_str.replace("Z", "+00:00"))
            target_date = start_at.date()
        except ValueError:
            return Response({"detail": "Invalid start_at format. Use ISO 8601"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            shop = Shop.objects.get(id=shop_id)
            service = Service.objects.get(id=service_id, shop=shop)
        except Shop.DoesNotExist:
            return Response({"detail": "Shop not found"}, status=status.HTTP_404_NOT_FOUND)
        except Service.DoesNotExist:
            return Response({"detail": "Service not found"}, status=status.HTTP_404_NOT_FOUND)

        # -----------------------------------------------------------------
        # 1. ACQUIRE LOCK (ProviderDayLock)
        # -----------------------------------------------------------------
        # We lock for all providers in the shop on that date to be safe if provider_id is null.
        # If provider_id is fixed, we could lock just that provider... 
        # but select_best_provider needs to see others too.
        # For simplicity and absolute safety, we lock the shop-date combination.
        
        # We'll lock an arbitrary record for this shop/date.
        # We created ProviderDayLock model for this purpose.
        
        lock_obj, _ = ProviderDayLock.objects.get_or_create(shop=shop, date=target_date)
        
        try:
            with transaction.atomic():
                # select_for_update blocks concurrent bookings for this shop/date
                locked_lock = ProviderDayLock.objects.select_for_update().get(id=lock_obj.id)
                
                # -----------------------------------------------------------------
                # 2. VALIDATE & SELECT PROVIDER
                # -----------------------------------------------------------------
                selected_provider = None
                
                if provider_id:
                    try:
                        provider = Provider.objects.get(id=provider_id, shop=shop, is_active=True)
                        valid_starts = provider_available_starts(provider, service, target_date)
                        # Check if requested start_at is in valid_starts
                        # Note: comparing aware datetimes. provider_available_starts returns them in local or UTC?
                        # It returns them in provider's timezone.
                        
                        # Normalize start_at to provider's timezone for comparison
                        tz_name = provider.availability_ruleset.timezone if provider.availability_ruleset else shop.time_zone
                        tz = pytz.timezone(tz_name)
                        local_start = start_at.astimezone(tz)
                        
                        is_valid = any(s == local_start for s in valid_starts)
                        if not is_valid:
                            return Response({"detail": "Requested time is no longer available for this provider."}, 
                                            status=status.HTTP_409_CONFLICT)
                        selected_provider = provider
                    except Provider.DoesNotExist:
                        return Response({"detail": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)
                else:
                    # Auto-assign best provider using the engine's selector
                    # First, we need to ensure the start_at is localized correctly for comparison within select_best_provider
                    # Actually, select_best_provider handles its own per-provider localization if we fix it there.
                    # For now, let's call it with shop-level info.
                    
                    selected_provider = select_best_provider(shop, service, target_date, start_at)
                    
                    if not selected_provider:
                        return Response({
                            "code": "NO_PROVIDER_AVAILABLE",
                            "detail": "No provider available for requested time."
                        }, status=status.HTTP_409_CONFLICT)

                # -----------------------------------------------------------------
                # 3. CREATE DYNAMIC SLOT + SLOTBOOKING
                # -----------------------------------------------------------------
                # Calculate end_time based on service duration
                duration_mins = service.duration or 30
                end_at = start_at + timedelta(minutes=duration_mins)
                
                # Create dynamic Slot (unique per service/start_time)
                from api.models import Slot, SlotBooking
                
                # Try to get existing slot or create new one
                # This handles edge case where slot already exists from pre-generation
                dynamic_slot, slot_created = Slot.objects.get_or_create(
                    service=service,
                    start_time=start_at,
                    defaults={
                        'shop': shop,
                        'end_time': end_at,
                        'capacity_left': 1,  # Will be decremented below
                    }
                )
                
                # Validate slot has capacity
                if dynamic_slot.capacity_left <= 0:
                    return Response({
                        "code": "SLOT_FULLY_BOOKED",
                        "detail": "This time slot is no longer available."
                    }, status=status.HTTP_409_CONFLICT)
                
                # Create SlotBooking with provider
                slot_booking = SlotBooking.objects.create(
                    user=request.user,
                    slot=dynamic_slot,
                    shop=shop,
                    service=service,
                    provider=selected_provider,  # Rule-based assignment
                    start_time=start_at,
                    end_time=end_at,
                    status='confirmed',
                    payment_status='pending'
                )
                
                # Decrement slot capacity
                dynamic_slot.capacity_left -= 1
                dynamic_slot.save(update_fields=['capacity_left'])
                
                # Return slot_id for client to call existing payment endpoint
                return Response({
                    "success": True,
                    "slot_id": dynamic_slot.id,
                    "slot_booking_id": slot_booking.id,
                    "provider_id": selected_provider.id,
                    "provider_name": selected_provider.name,
                    "start_at": start_at.isoformat(),
                    "end_at": end_at.isoformat(),
                    "service_id": service.id,
                    "shop_id": shop.id,
                    "next_step": f"POST /payments/payment-intent/{dynamic_slot.id}/"
                }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.exception("Booking creation failed")
            return Response({
                "code": "BOOKING_CREATION_FAILED",
                "detail": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

