# subscriptions/urls.py
from django.urls import path
from .views import (
    SubscriptionPlanListView,
    CreateSubscriptionCheckoutSessionView,
    CancelSubscriptionView,
)

urlpatterns = [
    path('plans/', SubscriptionPlanListView.as_view(), name='subscription-plans'),
    path('create-checkout-session/', CreateSubscriptionCheckoutSessionView.as_view(), name='create-checkout-session'),
    path('cancel-subscription/', CancelSubscriptionView.as_view(), name='cancel-subscription'),
]