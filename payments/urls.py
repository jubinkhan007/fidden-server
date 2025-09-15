from django.urls import path
from .views import (
    CreatePaymentIntentView,
    ShopOnboardingLinkView,
    SaveCardView,
    VerifyShopOnboardingView
)

urlpatterns = [
    path("payment-intent/<int:booking_id>/", CreatePaymentIntentView.as_view(), name="payment-intent"),
    path("shop-onboarding/<int:shop_id>/", ShopOnboardingLinkView.as_view(), name="shop-onboarding"),
    path("save-card/", SaveCardView.as_view(), name="save-card"),
    path("shops/verify-onboarding/<int:shop_id>", VerifyShopOnboardingView.as_view(), name="verify-shop-onboarding"),
]
