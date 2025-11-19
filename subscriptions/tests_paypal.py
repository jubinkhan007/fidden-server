from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch
from django.contrib.auth import get_user_model
from subscriptions.models import SubscriptionPlan, ShopSubscription
from api.models import Shop
from decimal import Decimal
from django.utils import timezone

from django.db import transaction
from unittest.mock import patch, MagicMock

User = get_user_model()

class PayPalSubscriptionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        
        # Mock Stripe to prevent API calls during Shop creation
        self.stripe_patcher = patch('stripe.Account.create')
        self.mock_stripe_create = self.stripe_patcher.start()
        self.mock_stripe_create.return_value = MagicMock(id='acct_test123')
        self.addCleanup(self.stripe_patcher.stop)

        # Create User and Shop
        self.user = User.objects.create_user(email='test@example.com', password='password', role='owner')
        self.shop = Shop.objects.create(
            owner=self.user, 
            name="Test Shop",
            capacity=5,
            start_at="09:00",
            close_at="17:00"
        )
        
        # Create Plans
        self.foundation_plan = SubscriptionPlan.objects.create(
            name=SubscriptionPlan.FOUNDATION,
            monthly_price=Decimal("0.00"),
            commission_rate=Decimal("0.00"),
            paypal_plan_id="P-FOUNDATION"
        )
        self.momentum_plan = SubscriptionPlan.objects.create(
            name=SubscriptionPlan.MOMENTUM,
            monthly_price=Decimal("29.00"),
            commission_rate=Decimal("10.00"),
            paypal_plan_id="P-MOMENTUM"
        )
        self.ai_plan = SubscriptionPlan.objects.create(
            name="AI Assistant",
            monthly_price=Decimal("10.00"),
            commission_rate=Decimal("0.00"),
            paypal_plan_id="P-AI-ADDON",
            ai_assistant=SubscriptionPlan.AI_ADDON
        )
        
        self.client.force_authenticate(user=self.user)

    @patch('subscriptions.views.create_subscription')
    def test_create_paypal_subscription(self, mock_create):
        mock_create.return_value = ('I-SUB123', 'https://paypal.com/approve')
        
        url = reverse('paypal-create-subscription')
        data = {'plan_id': self.momentum_plan.id}
        
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['subscription_id'], 'I-SUB123')
        self.assertEqual(response.data['approval_url'], 'https://paypal.com/approve')
        
        # Verify DB
        sub = ShopSubscription.objects.get(shop=self.shop)
        self.assertEqual(sub.paypal_subscription_id, 'I-SUB123')
        self.assertEqual(sub.status, 'pending')
        self.assertEqual(sub.plan, self.momentum_plan)

    @patch('subscriptions.views.revise_subscription')
    def test_update_paypal_subscription(self, mock_revise):
        # Setup existing subscription
        sub = ShopSubscription.objects.create(
            shop=self.shop,
            plan=self.momentum_plan,
            provider=ShopSubscription.PROVIDER_PAYPAL,
            paypal_subscription_id='I-EXISTING',
            status='active',
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=30)
        )
        
        mock_revise.return_value = {} # Success
        
        url = reverse('paypal-update-subscription')
        # Upgrade to a hypothetical Icon plan (using Foundation here just for ID, assuming it had a paypal ID)
        # Let's create an Icon plan
        icon_plan = SubscriptionPlan.objects.create(
            name=SubscriptionPlan.ICON,
            monthly_price=Decimal("49.00"),
            commission_rate=Decimal("5.00"),
            paypal_plan_id="P-ICON"
        )
        
        data = {'plan_id': icon_plan.id}
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        sub.refresh_from_db()
        self.assertEqual(sub.plan, icon_plan)

    @patch('subscriptions.views.cancel_subscription')
    def test_cancel_paypal_subscription(self, mock_cancel):
        mock_cancel.return_value = True
        
        sub = ShopSubscription.objects.create(
            shop=self.shop,
            plan=self.momentum_plan,
            provider=ShopSubscription.PROVIDER_PAYPAL,
            paypal_subscription_id='I-TO-CANCEL',
            status='active',
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=30)
        )
        
        url = reverse('paypal-cancel-subscription')
        data = {'reason': 'Testing'}
        
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        sub.refresh_from_db()
        self.assertEqual(sub.status, 'canceled')
        self.assertEqual(sub.plan, self.foundation_plan)
        self.assertIsNone(sub.paypal_subscription_id)

    @patch('subscriptions.views.create_subscription')
    def test_create_paypal_ai_addon(self, mock_create):
        mock_create.return_value = ('I-AI-123', 'https://paypal.com/approve-ai')
        
        url = reverse('paypal-create-ai-addon')
        data = {'plan_id': self.ai_plan.id}
        
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        sub = ShopSubscription.objects.get(shop=self.shop)
        self.assertEqual(sub.ai_paypal_subscription_id, 'I-AI-123')
        self.assertFalse(sub.ai_addon_active) # Pending webhook

    @patch('subscriptions.views.cancel_subscription')
    def test_cancel_paypal_ai_addon(self, mock_cancel):
        mock_cancel.return_value = True
        
        sub = ShopSubscription.objects.create(
            shop=self.shop,
            plan=self.momentum_plan,
            ai_provider=ShopSubscription.PROVIDER_PAYPAL,
            ai_paypal_subscription_id='I-AI-CANCEL',
            ai_addon_active=True
        )
        
        url = reverse('paypal-cancel-ai-addon')
        data = {'reason': 'No longer needed'}
        
        response = self.client.post(url, data)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        sub.refresh_from_db()
        self.assertFalse(sub.ai_addon_active)
        self.assertIsNone(sub.ai_paypal_subscription_id)


class PayPalWebhookTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        
        # Mock Stripe
        self.stripe_patcher = patch('stripe.Account.create')
        self.mock_stripe_create = self.stripe_patcher.start()
        self.mock_stripe_create.return_value = MagicMock(id='acct_test123')
        self.addCleanup(self.stripe_patcher.stop)

        self.user = User.objects.create_user(email='web@test.com', password='password', role='owner')
        self.shop = Shop.objects.create(
            owner=self.user, 
            name="Web Shop",
            capacity=5,
            start_at="09:00",
            close_at="17:00"
        )
        self.plan = SubscriptionPlan.objects.create(
            name=SubscriptionPlan.MOMENTUM, 
            paypal_plan_id="P-MOM",
            monthly_price=Decimal("29.00"),
            commission_rate=Decimal("10.00")
        )

    def test_webhook_subscription_activated(self):
        sub = ShopSubscription.objects.create(
            shop=self.shop,
            plan=self.plan,
            provider=ShopSubscription.PROVIDER_PAYPAL,
            paypal_subscription_id='I-WEB-ACTIVATE',
            status='pending',
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=30)
        )
        
        url = reverse('paypal-webhook')
        data = {
            "event_type": "BILLING.SUBSCRIPTION.ACTIVATED",
            "resource": {
                "id": "I-WEB-ACTIVATE",
                "billing_info": {"next_billing_time": "2025-01-01T00:00:00Z"}
            }
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        sub.refresh_from_db()
        self.assertEqual(sub.status, 'active')

    def test_webhook_subscription_cancelled(self):
        sub = ShopSubscription.objects.create(
            shop=self.shop,
            plan=self.plan,
            provider=ShopSubscription.PROVIDER_PAYPAL,
            paypal_subscription_id='I-WEB-CANCEL',
            status='active',
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=30)
        )
        
        url = reverse('paypal-webhook')
        data = {
            "event_type": "BILLING.SUBSCRIPTION.CANCELLED",
            "resource": {
                "id": "I-WEB-CANCEL"
            }
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        sub.refresh_from_db()
        self.assertEqual(sub.status, 'canceled')
        self.assertIsNone(sub.paypal_subscription_id)

    def test_webhook_ai_addon_activated(self):
        sub = ShopSubscription.objects.create(
            shop=self.shop,
            plan=self.plan,
            ai_provider=ShopSubscription.PROVIDER_PAYPAL,
            ai_paypal_subscription_id='I-AI-ACTIVATE',
            ai_addon_active=False,
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=30)
        )
        
        url = reverse('paypal-webhook')
        data = {
            "event_type": "BILLING.SUBSCRIPTION.ACTIVATED",
            "resource": {
                "id": "I-AI-ACTIVATE"
            }
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        sub.refresh_from_db()
        self.assertTrue(sub.ai_addon_active)
