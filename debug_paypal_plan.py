import os
import django
import requests
import base64
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fidden.settings")
django.setup()

from django.conf import settings
from subscriptions.models import SubscriptionPlan

def get_access_token(client_id, secret, base_url):
    print(f"Getting access token from {base_url}...")
    basic_auth = base64.b64encode(f"{client_id}:{secret}".encode("utf-8")).decode("utf-8")
    resp = requests.post(
        f"{base_url}/v1/oauth2/token",
        headers={
            "Authorization": f"Basic {basic_auth}",
            "Accept": "application/json",
        },
        data={"grant_type": "client_credentials"},
    )
    if resp.status_code != 200:
        print(f"Failed to get token: {resp.status_code} {resp.text}")
        return None
    return resp.json().get("access_token")

def check_plan(plan_id, access_token, base_url):
    print(f"Checking Plan ID: {plan_id}...")
    resp = requests.get(
        f"{base_url}/v1/billing/plans/{plan_id}",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
    )
    if resp.status_code == 200:
        print(f"✅ Plan found: {resp.json().get('name')} ({resp.json().get('status')})")
        return True
    else:
        print(f"❌ Plan check failed: {resp.status_code}")
        print(f"Response: {resp.text}")
        return False

def main():
    client_id = settings.PAYPAL_CLIENT_ID
    secret = settings.PAYPAL_SECRET
    base_url = settings.PAYPAL_BASE_URL or "https://api-m.sandbox.paypal.com"

    if not client_id or not secret:
        print("PAYPAL_CLIENT_ID or PAYPAL_SECRET not set.")
        return

    token = get_access_token(client_id, secret, base_url)
    if not token:
        return

    print("\nChecking Plans in Database:")
    plans = SubscriptionPlan.objects.exclude(paypal_plan_id__isnull=True).exclude(paypal_plan_id="")
    
    if not plans.exists():
        print("No plans with PayPal IDs found in DB.")
    
    for plan in plans:
        print(f"\n--- Plan: {plan.name} ---")
        print(f"DB PayPal ID: {plan.paypal_plan_id}")
        check_plan(plan.paypal_plan_id, token, base_url)

if __name__ == "__main__":
    main()
