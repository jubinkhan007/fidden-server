from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Avg

from .models import Shop, Service, RatingReview, ServiceCategory
from .serializers import ShopSerializer, ServiceSerializer, RatingReviewSerializer, ServiceCategorySerializer
from .permissions import IsOwnerAndOwnerRole, IsOwnerRole


class ShopListCreateView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]

    def get(self, request):
        user = request.user
        if getattr(user, 'role', None) != 'owner':
            return Response({"detail": "You do not have a shop."}, status=status.HTTP_403_FORBIDDEN)

        shop = Shop.objects.filter(owner=user).first()
        if not shop:
            return Response({"detail": "No shop found for this user."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ShopSerializer(shop, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        if getattr(request.user, 'role', None) != 'owner':
            return Response({"detail": "Only owners can create shops."}, status=status.HTTP_403_FORBIDDEN)

        if hasattr(request.user, 'shop'):
            return Response({"detail": "You already have a shop."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = ShopSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            shop = serializer.save(owner=request.user)
            return Response(ShopSerializer(shop, context={'request': request}).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ShopRetrieveUpdateDestroyView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]

    def get_object(self, pk):
        return get_object_or_404(Shop, pk=pk, owner=self.request.user)

    def get(self, request, pk):
        shop = self.get_object(pk)
        serializer = ShopSerializer(shop, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk):
        shop = self.get_object(pk)
        serializer = ShopSerializer(shop, data=request.data, context={'request': request})
        if serializer.is_valid():
            shop = serializer.save(owner=request.user)
            return Response(ShopSerializer(shop, context={'request': request}).data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        shop = self.get_object(pk)
        serializer = ShopSerializer(shop, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            shop = serializer.save(owner=request.user)
            return Response(ShopSerializer(shop, context={'request': request}).data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        shop = self.get_object(pk)
        shop.delete()
        return Response({"success": True, "message": "Shop deleted successfully."}, status=status.HTTP_200_OK)


class ServiceCategoryListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsOwnerAndOwnerRole]
    
    def get(self, request):
        categories = ServiceCategory.objects.all()
        serializer = ServiceCategorySerializer(categories, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ServiceListCreateView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsOwnerRole]

    def get(self, request):
        shop = Shop.objects.filter(owner=request.user).first()
        if not shop:
            return Response({"detail": "You must create a shop before accessing services."}, status=status.HTTP_400_BAD_REQUEST)

        services = shop.services.all()
        serializer = ServiceSerializer(services, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        shop = Shop.objects.filter(owner=request.user).first()
        if not shop:
            return Response({"detail": "You must create a shop before adding services."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = ServiceSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            service = serializer.save(shop=shop)
            return Response(ServiceSerializer(service, context={'request': request}).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ServiceRetrieveUpdateDestroyView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsOwnerRole]

    def get_object(self, request, pk):
        shop = Shop.objects.filter(owner=request.user).first()
        if not shop:
            return None
        return get_object_or_404(Service, pk=pk, shop=shop)

    def get(self, request, pk):
        service = self.get_object(request, pk)
        if not service:
            return Response({"detail": "You must create a shop before accessing services."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = ServiceSerializer(service, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk):
        service = self.get_object(request, pk)
        if not service:
            return Response({"detail": "You must create a shop before updating services."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = ServiceSerializer(service, data=request.data, context={'request': request})
        if serializer.is_valid():
            service = serializer.save()
            return Response(ServiceSerializer(service, context={'request': request}).data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        service = self.get_object(request, pk)
        if not service:
            return Response({"detail": "You must create a shop before updating services."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = ServiceSerializer(service, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            service = serializer.save()
            return Response(ServiceSerializer(service, context={'request': request}).data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        service = self.get_object(request, pk)
        if not service:
            return Response({"detail": "You must create a shop before deleting services."}, status=status.HTTP_400_BAD_REQUEST)

        service.delete()
        return Response({"success": True, "message": "Service deleted successfully."}, status=status.HTTP_200_OK)


class UserRatingReviewView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if getattr(user, 'role', None) != 'user':
            return Response({"detail": "Only users can view reviews."}, status=status.HTTP_403_FORBIDDEN)

        shop_id = request.query_params.get('shop')
        service_id = request.query_params.get('service')

        reviews = RatingReview.objects.filter(user__role='user')

        if shop_id:
            reviews = reviews.filter(shop_id=shop_id)
        if service_id:
            reviews = reviews.filter(service_id=service_id)

        avg_rating = reviews.aggregate(avg=Avg('rating'))['avg'] or 0
        total_reviews = reviews.count()

        serializer = RatingReviewSerializer(reviews, many=True, context={'request': request})
        return Response({
            "average_rating": round(avg_rating, 2),
            "total_reviews": total_reviews,
            "reviews": serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request):
        user = request.user
        if getattr(user, 'role', None) != 'user':
            return Response({"detail": "Only users can create reviews."}, status=status.HTTP_403_FORBIDDEN)

        serializer = RatingReviewSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            review = serializer.save()
            return Response(RatingReviewSerializer(review, context={'request': request}).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
