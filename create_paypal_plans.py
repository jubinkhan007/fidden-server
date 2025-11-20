import os
import django
import requests
import base64
import json

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fidden.settings")
django.setup()

from django.conf import settings

def get_access_token(client_id, secret, base_url):
    basic_auth = base64.b64encode(f"{client_id}:{secret}".encode("utf-8")).decode("utf-8")
    resp = requests.post(
        f"{base_url}/v1/oauth2/token",
        headers={
            "Authorization": f"Basic {basic_auth}",
            "Accept": "application/json",
        },
        data={"grant_type": "client_credentials"},
    )
    resp.raise_for_status()
    return resp.json().get("access_token")

def create_product(access_token, base_url):
    print("Creating Product 'Fidden Subscriptions'...")
    payload = {
        "name": "Fidden Subscriptions",
        "description": "Subscription plans for Fidden Shop Owners",
        "type": "SERVICE",
        "category": "SOFTWARE",
    }
    resp = requests.post(
        f"{base_url}/v1/catalogs/products",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=payload,
    )
    if resp.status_code == 201:
        product_id = resp.json()["id"]
        print(f"✅ Product created: {product_id}")
        return product_id
    else:
        print(f"❌ Failed to create product: {resp.text}")
        return None

def create_plan(access_token, base_url, product_id, name, price, description):
    print(f"Creating Plan '{name}' (${price})...")
    payload = {
        "product_id": product_id,
        "name": name,
        "description": description,
        "status": "ACTIVE",
        "billing_cycles": [
            {
                "frequency": {
                    "interval_unit": "MONTH",
                    "interval_count": 1
                },
                "tenure_type": "REGULAR",
                "sequence": 1,
                "total_cycles": 0, # infinite
                "pricing_scheme": {
                    "fixed_price": {
                        "value": str(price),
                        "currency_code": "USD"
                    }
                }
            }
        ],
        "payment_preferences": {
            "auto_bill_outstanding": True,
            "setup_fee_failure_action": "CONTINUE",
            "payment_failure_threshold": 3
        },
    }
    
    resp = requests.post(
        f"{base_url}/v1/billing/plans",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=payload,
    )
    
    if resp.status_code == 201:
        plan_id = resp.json()["id"]
        print(f"✅ Plan created: {name} -> ID: {plan_id}")
        return plan_id
    else:
        print(f"❌ Failed to create plan {name}: {resp.text}")
        return None

def main():
    client_id = settings.PAYPAL_CLIENT_ID
    secret = settings.PAYPAL_SECRET
    base_url = settings.PAYPAL_BASE_URL or "https://api-m.sandbox.paypal.com"

    if not client_id or not secret:
        print("PAYPAL_CLIENT_ID or PAYPAL_SECRET not set.")
        return

    try:
        token = get_access_token(client_id, secret, base_url)
    except Exception as e:
        print(f"Failed to authenticate: {e}")
        return

    product_id = create_product(token, base_url)
    if not product_id:
        return

    print("\n--- CREATED PLAN IDS ---")
    print("Copy these into your .env file or Render environment variables:\n")

    momentum_id = create_plan(token, base_url, product_id, "Momentum", "29.00", "Momentum Tier Subscription")
    if momentum_id:
        print(f"PAYPAL_PLAN_MOMENTUM_ID={momentum_id}")

    icon_id = create_plan(token, base_url, product_id, "Icon", "49.00", "Icon Tier Subscription")
    if icon_id:
        print(f"PAYPAL_PLAN_ICON_ID={icon_id}")

    ai_id = create_plan(token, base_url, product_id, "AI Assistant", "10.00", "AI Assistant Add-on")
    if ai_id:
        print(f"PAYPAL_PLAN_AI_ADDON_ID={ai_id}")

    print("\n------------------------")
    print("After updating your environment variables, run:")
    print("python manage.py sync_paypal_plans")

if __name__ == "__main__":
    main()
