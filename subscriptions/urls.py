# subscriptions/urls.py
from django.urls import path
from .views import (
    CancelAIAddonView,
    CreateAIAddonCheckoutSessionView,
    SubscriptionPlanListView,
    CreateSubscriptionCheckoutSessionView,
    CancelSubscriptionView,
    SubscriptionDetailsView,
    CheckoutReturnView,    # <- ensure imported
    CheckoutCancelView,    # <- ensure imported
    CreatePayPalSubscriptionView,
    UpdatePayPalSubscriptionView,
    CancelPayPalSubscriptionView,
    CreatePayPalAiAddonView,
    CancelPayPalAiAddonView,
    PayPalReturnView,
    PayPalCancelView,
)

urlpatterns = [
    path("plans/", SubscriptionPlanListView.as_view(), name="subscription-plans"),
    path("details/", SubscriptionDetailsView.as_view(), name="subscription-details"),
    path("create-checkout-session/", CreateSubscriptionCheckoutSessionView.as_view(),
         name="create-checkout-session"),
    path("cancel-subscription/", CancelSubscriptionView.as_view(), name="cancel-subscription"),

    # HTTPS landers that immediately deep-link back to the app
    path("checkout/return/", CheckoutReturnView.as_view(), name="checkout_return"),
    path("checkout/cancel/", CheckoutCancelView.as_view(), name="checkout_cancel"),
    path("create-ai-addon-checkout-session/", CreateAIAddonCheckoutSessionView.as_view(), name="create-ai-addon-checkout-session"),
    path("cancel-ai-addon/", CancelAIAddonView.as_view(), name="cancel-ai-addon"),

    # PayPal
    path("paypal/create-subscription/", CreatePayPalSubscriptionView.as_view(), name="paypal-create-subscription"),
    path("paypal/update-subscription/", UpdatePayPalSubscriptionView.as_view(), name="paypal-update-subscription"),
    path("paypal/cancel-subscription/", CancelPayPalSubscriptionView.as_view(), name="paypal-cancel-subscription"),
    path("paypal/create-ai-addon/", CreatePayPalAiAddonView.as_view(), name="paypal-create-ai-addon"),
    path("paypal/cancel-ai-addon/", CancelPayPalAiAddonView.as_view(), name="paypal-cancel-ai-addon"),
    path("paypal/return/", PayPalReturnView.as_view(), name="paypal_return"),
    path("paypal/cancel/", PayPalCancelView.as_view(), name="paypal_cancel"),
]
