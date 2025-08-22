from django.urls import path
from .views import (
    ShopListCreateView,
    ShopRetrieveUpdateDestroyView,
    ServiceListCreateView,
    ServiceRetrieveUpdateDestroyView,
    UserRatingReviewView,
    ServiceCategoryListView
)

urlpatterns = [
    path('shop/', ShopListCreateView.as_view(), name='shop-list-create'),
    path('shop/<int:pk>/', ShopRetrieveUpdateDestroyView.as_view(), name='shop-detail'),
    path('services/', ServiceListCreateView.as_view(), name='service-list-create'),
    path('services/<int:pk>/', ServiceRetrieveUpdateDestroyView.as_view(), name='service-detail'),
    path('reviews/', UserRatingReviewView.as_view(), name='user-reviews'),
    path('categories/', ServiceCategoryListView.as_view(), name='category-list')
]
