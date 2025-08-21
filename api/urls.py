from django.urls import path
from .views import ShopListCreateView, ShopRetrieveUpdateDestroyView

urlpatterns = [
    path('shop/', ShopListCreateView.as_view(), name='shop-list-create'),
    path('shop/<int:pk>/', ShopRetrieveUpdateDestroyView.as_view(), name='shop-detail'),
]
