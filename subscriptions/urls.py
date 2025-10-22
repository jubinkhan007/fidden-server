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
]
