import logging
from datetime import datetime, date, timedelta


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
from api.serializers import ProviderSerializer

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
            if not shop.use_rule_based_availability:
                 # If disabled, maybe return empty list/404? 
                 # Let's return 400 to signal client to use legacy.
                return Response({"detail": "This shop does not support rule-based availability."}, status=status.HTTP_400_BAD_REQUEST)

            service = Service.objects.get(id=service_id, shop=shop)
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except Shop.DoesNotExist:
            return Response({"detail": "Shop not found"}, status=status.HTTP_404_NOT_FOUND)
        except Service.DoesNotExist:
            return Response({"detail": "Service not found or dose not belong to shop"}, status=status.HTTP_404_NOT_FOUND)
        except ValueError:
            return Response({"detail": "Invalid date format. Use YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST)

        # Resolve timezone_id for response
        from api.utils.availability import resolve_timezone_id, to_utc
        
        if provider_id:
            try:
                provider = Provider.objects.get(id=provider_id, shop=shop)
                available_times = provider_available_starts(provider, service, target_date)
                timezone_id = resolve_timezone_id(provider)
            except Provider.DoesNotExist:
                return Response({"detail": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)
            
            # Format: list of ISO timestamps with offsets
            available_slots = []
            for dt in available_times:
                available_slots.append({
                    "start_at": dt.isoformat(),
                    "start_at_utc": to_utc(dt).strftime("%Y-%m-%dT%H:%M:%SZ")
                })
        else:
            # Aggregate across all providers
            available_times = get_any_provider_availability(shop, service, target_date)
            
            # Resolve timezone from first active provider or shop default
            first_provider = Provider.objects.filter(shop=shop, is_active=True).first()
            timezone_id = resolve_timezone_id(first_provider) if first_provider else shop.time_zone or 'America/New_York'
            
            # Format: list of dicts with start_time, availability_count, ISO timestamp
            available_slots = []
            for item in available_times:
                dt = item["start_time"]
                available_slots.append({
                    "start_at": dt.isoformat(),
                    "start_at_utc": to_utc(dt).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "availability_count": item["available_count"]
                })
        
        return Response({
            "date": date_str,
            "shop_id": int(shop_id),
            "service_id": int(service_id),
            "timezone_id": timezone_id,
            "available_slots": available_slots
        })


class ProvidersView(APIView):
    """
    List providers for a specific shop, optionally filtering by service.
    Create a new provider for the shop (Owner only).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, shop_id):
        service_id = request.query_params.get('service_id')
        
        qs = Provider.objects.filter(shop_id=shop_id, is_active=True)
        
        if service_id:
            # Filter providers who can perform this service
            qs = qs.filter(services__id=service_id)
            
        data = [{
            "id": p.id,
            "name": p.name,
            "profile_image": p.profile_image.url if p.profile_image else None,
            "allow_any_provider_booking": p.allow_any_provider_booking
        } for p in qs]
        
        return Response(data)

    def post(self, request, shop_id):
        """Create a new provider."""
        try:
            shop = Shop.objects.get(id=shop_id)
        except Shop.DoesNotExist:
            return Response({"detail": "Shop not found"}, status=status.HTTP_404_NOT_FOUND)

        if shop.owner != request.user:
            return Response({"detail": "You do not have permission to add providers to this shop."}, status=status.HTTP_403_FORBIDDEN)

        serializer = ProviderSerializer(data=request.data)
        if serializer.is_valid():
            provider = serializer.save(shop=shop)
            # Add services if provided (M2M handling)
            if 'services' in request.data:
                # Serializer handles M2M if passed as list of IDs, 
                # but if we need custom logic we can do it here. 
                # ProviderSerializer already has services field.
                pass
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProviderDetailView(APIView):
    """
    Retrieve, Update, or Delete a provider (Owner only).
    """
    permission_classes = [IsAuthenticated]

    def get_object(self, pk, user):
        try:
            provider = Provider.objects.get(pk=pk)
            # Ensure user owns the shop this provider belongs to
            if provider.shop.owner != user:
                return None
            return provider
        except Provider.DoesNotExist:
            return None

    def patch(self, request, pk):
        provider = self.get_object(pk, request.user)
        if not provider:
            return Response({"detail": "Provider not found or permission denied"}, status=status.HTTP_404_NOT_FOUND)

        serializer = ProviderSerializer(provider, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        provider = self.get_object(pk, request.user)
        if not provider:
            return Response({"detail": "Provider not found or permission denied"}, status=status.HTTP_404_NOT_FOUND)

        # Soft delete
        provider.is_active = False
        provider.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

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
                # 2. SELECT CANDIDATE PROVIDERS (Ranked List)
                # -----------------------------------------------------------------
                from api.utils.availability import get_ranked_providers
                
                candidate_providers = []
                
                if provider_id:
                     try:
                         # Explicit provider: one candidate
                         p = Provider.objects.get(id=provider_id, shop=shop, is_active=True)
                         candidate_providers.append(p)
                     except Provider.DoesNotExist:
                         return Response({"detail": "Provider not found"}, status=status.HTTP_404_NOT_FOUND)
                else:
                     # Any provider: get ranked list
                      candidate_providers = get_ranked_providers(shop, service, target_date, start_at)
                      
                if not candidate_providers:
                     return Response({
                         "code": "NO_PROVIDER_AVAILABLE",
                         "detail": "No providers available."
                     }, status=status.HTTP_409_CONFLICT)
                
                # -----------------------------------------------------------------
                # 2.5 DST VALIDATION: Reject bookings at non-existent local times
                # -----------------------------------------------------------------
                from api.utils.availability import resolve_timezone_id, safe_localize, to_utc
                from zoneinfo import ZoneInfo
                
                # Use first candidate to determine timezone for validation
                tz_id = resolve_timezone_id(candidate_providers[0])
                
                # Convert incoming start_at (which is in UTC or has offset) to local wall time
                local_tz = ZoneInfo(tz_id)
                start_at_local = start_at.astimezone(local_tz)
                
                # Extract wall time and re-localize to check if it exists
                wall_time_str = start_at_local.strftime("%H:%M")
                validated_dt = safe_localize(target_date, wall_time_str, tz_id)
                
                if validated_dt is None:
                    # Spring-forward gap: this local wall time doesn't exist
                    return Response({
                        "code": "INVALID_TIME",
                        "detail": f"The requested time {wall_time_str} does not exist on {target_date} due to DST transition."
                    }, status=status.HTTP_400_BAD_REQUEST)
                     
                # -----------------------------------------------------------------
                # 3. ATTEMPT BOOKING (Retry Loop)
                # -----------------------------------------------------------------
                selected_provider = None
                
                for candidate in candidate_providers:
                    # VALIDATE availability for this specific provider
                    valid_starts = provider_available_starts(candidate, service, target_date)
                    
                    # Normalize start_at to provider's timezone for comparison
                    cand_tz_id = resolve_timezone_id(candidate)
                    cand_tz = ZoneInfo(cand_tz_id)
                    local_start = start_at.astimezone(cand_tz)
                    
                    if any(s == local_start for s in valid_starts):
                        selected_provider = candidate
                        break # Success!
                
                if not selected_provider:
                     return Response({
                         "code": "NO_PROVIDER_AVAILABLE",
                         "detail": "Selected time is no longer available."
                     }, status=status.HTTP_409_CONFLICT)

                # -----------------------------------------------------------------
                # 4. CREATE DYNAMIC SLOT + SLOTBOOKING
                # -----------------------------------------------------------------
                # Calculate end_time based on service duration
                duration_mins = service.duration or 30
                end_at = start_at + timedelta(minutes=duration_mins)
                
                # Create dynamic Slot (unique per service/start_time)
                from api.models import Slot, SlotBooking
                
                # Try to get existing slot or create new one
                dynamic_slot, slot_created = Slot.objects.get_or_create(
                    service=service,
                    start_time=start_at,
                    defaults={
                        'shop': shop,
                        'end_time': end_at,
                        'capacity_left': 10,
                    }
                )
                
                # Validate slot has capacity
                if dynamic_slot.capacity_left <= 0:
                    return Response({
                        "code": "NO_PROVIDER_AVAILABLE",
                        "detail": "This time slot is no longer available."
                    }, status=status.HTTP_409_CONFLICT)
                
                # Create SlotBooking with provider
                slot_booking = SlotBooking.objects.create(
                    user=request.user,
                    slot=dynamic_slot,
                    shop=shop,
                    service=service,
                    provider=selected_provider,
                    start_time=start_at,
                    end_time=end_at,
                    status='confirmed',
                    payment_status='pending'
                )
                
                # Decrement slot capacity
                dynamic_slot.capacity_left -= 1
                dynamic_slot.save(update_fields=['capacity_left'])
                
                # Convert times for response
                final_tz_id = resolve_timezone_id(selected_provider)
                final_tz = ZoneInfo(final_tz_id)
                start_at_local_resp = start_at.astimezone(final_tz)
                end_at_local_resp = end_at.astimezone(final_tz)
                
                return Response({
                    "success": True,
                    "booking_id": slot_booking.id,
                    "slot_id": dynamic_slot.id,
                    "provider_id": selected_provider.id,
                    "provider_name": selected_provider.name,
                    "timezone_id": final_tz_id,
                    "start_at": start_at_local_resp.isoformat(),
                    "start_at_utc": to_utc(start_at).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "end_at": end_at_local_resp.isoformat(),
                    "end_at_utc": to_utc(end_at).strftime("%Y-%m-%dT%H:%M:%SZ"),
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

