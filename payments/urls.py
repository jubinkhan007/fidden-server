from django.urls import path
from .views import (
    CapturePayPalAIAddonOrderView,
    CapturePayPalOrderView,
    CapturePayPalSubscriptionOrderView,
    CreatePayPalAIAddonOrderView,
    CreatePayPalOrderView,
    CreatePayPalSubscriptionOrderView,
    CreatePaymentIntentView,
    MarkBookingNoShowView,
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
    path('bookings/<int:booking_id>/mark-no-show/', MarkBookingNoShowView.as_view(), name='mark-booking-no-show'),
    path('paypal/create-order/<int:slot_id>/', CreatePayPalOrderView.as_view(), name='paypal-create'),
    path('paypal/capture-order/', CapturePayPalOrderView.as_view(), name='paypal-capture'),
    path(
        "paypal/subscription/create-order/",
        CreatePayPalSubscriptionOrderView.as_view(),
        name="paypal-subscription-create-order",
    ),
    path(
        "paypal/subscription/capture-order/",
        CapturePayPalSubscriptionOrderView.as_view(),
        name="paypal-subscription-capture-order",
    ),

    # NEW: AI add-on via PayPal
    path(
        "paypal/ai-addon/create-order/",
        CreatePayPalAIAddonOrderView.as_view(),
        name="paypal-ai-addon-create-order",
    ),
    path(
        "paypal/ai-addon/capture-order/",
        CapturePayPalAIAddonOrderView.as_view(),
        name="paypal-ai-addon-capture-order",
    ),

]
