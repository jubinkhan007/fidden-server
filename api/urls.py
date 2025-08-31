from django.urls import path
from .views import (
    ShopListCreateView,
    ShopRetrieveUpdateDestroyView,
    ServiceListCreateView,
    ServiceRetrieveUpdateDestroyView,
    UserRatingReviewView,
    ServiceCategoryListView,
    SlotListView,
    SlotBookingView,
    CancelSlotBookingView,
    AllShopsListView,
    ShopDetailView,
    AllServicesListView,
    ServiceDetailView,
    FavoriteShopView,
    PromotionListView,
    ServiceWishlistView
)

urlpatterns = [
    path('shop/', ShopListCreateView.as_view(), name='shop-list-create'),
    path('shop/<int:pk>/', ShopRetrieveUpdateDestroyView.as_view(), name='shop-detail'),
    path('services/', ServiceListCreateView.as_view(), name='service-list-create'),
    path('services/<int:pk>/', ServiceRetrieveUpdateDestroyView.as_view(), name='service-detail'),
    path('reviews/', UserRatingReviewView.as_view(), name='user-reviews'),
    path('categories/', ServiceCategoryListView.as_view(), name='category-list'),
    path('shops/<int:shop_id>/slots/', SlotListView.as_view(), name='slot-list'),
    path('slot-booking/', SlotBookingView.as_view(), name='slot-booking-create'),
    path('slot-booking/<int:booking_id>/cancel/', CancelSlotBookingView.as_view(), name='slot-booking-cancel'),
    path('users/shops/', AllShopsListView.as_view(), name='all-shops-list-user'),
    path('users/shops/details/<int:shop_id>/', ShopDetailView.as_view(), name='shop-detail-user'),
    path("users/services/", AllServicesListView.as_view(), name="all-services"),
    path("users/services/<int:service_id>/", ServiceDetailView.as_view(), name="service-detail"),
    path('favorite-shop/', FavoriteShopView.as_view(), name='favorite-shop'),
    path('promotions/', PromotionListView.as_view(), name='promotion-list'),
    path('users/service-wishlist/', ServiceWishlistView.as_view(), name='service-wishlist'),

]
