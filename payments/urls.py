from django.urls import path
from .views import (
    CreatePaymentIntentView,
    ShopOnboardingLinkView,
    SaveCardView,
    VerifyShopOnboardingView,
    BookingListView,
    CancelBookingView,
    TransactionLogListView,
    StripeReturnView,     
    StripeRefreshView,
    RemainingPaymentView,
)

urlpatterns = [
    path("payment-intent/<int:slot_id>/", CreatePaymentIntentView.as_view(), name="payment-intent"),
    path("shop-onboarding/<int:shop_id>/", ShopOnboardingLinkView.as_view(), name="shop-onboarding"),
    path("save-card/", SaveCardView.as_view(), name="save-card"),
    path("shops/verify-onboarding/<int:shop_id>/", VerifyShopOnboardingView.as_view(), name="verify-shop-onboarding"),
    path("bookings/", BookingListView.as_view(), name="booking-list"),
    path("bookings/cancel/<int:booking_id>/", CancelBookingView.as_view(), name="cancel-booking"),
    path("bookings/remaining-payment/<int:booking_id>/", RemainingPaymentView.as_view(), name="remaining-payment"),
    path("transactions/", TransactionLogListView.as_view(), name="transaction-list"),
    path("stripe/return/",  StripeReturnView.as_view(),  name="stripe-return"),
    path("stripe/refresh/", StripeRefreshView.as_view(), name="stripe-refresh"),
]
