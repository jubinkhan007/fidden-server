from django.urls import path
from .views import (
    CreatePaymentIntentView,
    ShopOnboardingLinkView,
    SaveCardView,
    StripeWebhookView
)

urlpatterns = [
    path("payment-intent/<int:booking_id>/", CreatePaymentIntentView.as_view(), name="payment-intent"),
    path("shop-onboarding/<int:shop_id>/", ShopOnboardingLinkView.as_view(), name="shop-onboarding"),
    path("save-card/", SaveCardView.as_view(), name="save-card"),
    path("stripe-webhook/", StripeWebhookView, name="stripe-webhook"),
]
