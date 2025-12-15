#!/usr/bin/env python
"""
Seed Design Requests for Shop 1 (Tattoo Artist)
Run: python seed_design_requests.py
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fidden.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from api.models import Shop, DesignRequest
from accounts.models import User

def seed_design_requests():
    # Get shop 1
    try:
        shop = Shop.objects.get(id=1)
        print(f"✓ Found shop: {shop.name}")
    except Shop.DoesNotExist:
        print("✗ Shop 1 not found!")
        return
    
    # Find or create a test customer
    customer, created = User.objects.get_or_create(
        email="tattoo_customer@example.com",
        defaults={
            'name': 'Jordan Lee',
            'role': 'user',
            'is_active': True,
        }
    )
    if created:
        customer.set_password('testpass123')
        customer.save()
        print(f"✓ Created test customer: {customer.email}")
    else:
        print(f"✓ Found existing customer: {customer.email}")
    
    # Sample design requests
    designs = [
        {
            'description': 'I want a dragon on my arm with fire breathing effects. Looking for something bold and dynamic.',
            'placement': 'Left Forearm',
            'size_approx': '6 x 4 inches',
            'status': 'pending',
        },
        {
            'description': 'Geometric wolf design with mandala patterns incorporated. Prefer black and grey.',
            'placement': 'Upper Back',
            'size_approx': '8 x 6 inches',
            'status': 'discussing',
        },
        {
            'description': 'Minimalist mountain range with forest silhouette. Fine line work preferred.',
            'placement': 'Inner Bicep',
            'size_approx': '4 x 3 inches',
            'status': 'approved',
        },
        {
            'description': 'Traditional Japanese koi fish swimming upstream with cherry blossoms.',
            'placement': 'Right Thigh',
            'size_approx': '10 x 6 inches',
            'status': 'pending',
        },
        {
            'description': 'Small anchor with "Stay Grounded" text in script font.',
            'placement': 'Wrist',
            'size_approx': '2 x 2 inches',
            'status': 'approved',
        },
    ]
    
    created_count = 0
    for design_data in designs:
        design, created = DesignRequest.objects.get_or_create(
            shop=shop,
            user=customer,
            description=design_data['description'],
            defaults={
                'placement': design_data['placement'],
                'size_approx': design_data['size_approx'],
                'status': design_data['status'],
            }
        )
        if created:
            created_count += 1
            print(f"  ✓ Created: {design_data['placement']} - {design_data['status']}")
        else:
            print(f"  ~ Already exists: {design_data['placement']}")
    
    print(f"\n✅ Done! Created {created_count} new design requests for shop {shop.name}")
    
    # Show current count
    total = DesignRequest.objects.filter(shop=shop).count()
    print(f"Total design requests for shop: {total}")

if __name__ == '__main__':
    seed_design_requests()
