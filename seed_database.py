#!/usr/bin/env python
"""
Database Seed Script - Create Sample Data for Fidden

This script populates a fresh database with:
- Test users (owner, customer)
- Shops with different niches
- Services
- Sample bookings
- Tattoo artist specific data (for tattoo_artist niche)
"""
import os
import django
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fidden.settings')
django.setup()

from django.contrib.auth import get_user_model
from api.models import (
    Shop, Service, ServiceCategory, SlotBooking, Slot,
    PortfolioItem, DesignRequest, ConsentFormTemplate, SignedConsentForm,
    IDVerificationRequest
)
from payments.models import Booking
from subscriptions.models import SubscriptionPlan, ShopSubscription
from datetime import datetime, timedelta
from django.utils import timezone

User = get_user_model()

def create_users():
    """Create test users"""
    print("\n📝 Creating users...")
    
    # Admin user
    admin, created = User.objects.get_or_create(
        email='admin@fidden.com',
        defaults={
            'name': 'Admin User',
            'role': 'admin',
            'is_staff': True,
            'is_superuser': True,
            'is_verified': True,
        }
    )
    if created:
        admin.set_password('admin123')
        admin.save()
        print(f"  ✓ Created admin: {admin.email}")
    
    # Shop owners
    owners_data = [
        ('barbershop@fidden.com', 'Bob the Barber', 'barber'),
        ('tattoo@fidden.com', 'Ink Master', 'tattoo_artist'),
        ('nails@fidden.com', 'Nail Queen', 'nail_tech'),
        ('fitness@fidden.com', 'Fit Pro', 'fitness_trainer'),
    ]
    
    owners = {}
    for email, name, niche in owners_data:
        owner, created = User.objects.get_or_create(
            email=email,
            defaults={
                'name': name,
                'role': 'owner',
                'is_verified': True,
            }
        )
        if created:
            owner.set_password('owner123')
            owner.save()
            print(f"  ✓ Created owner: {owner.email}")
        owners[niche] = owner
    
    # Customers
    customers = []
    for i in range(1, 6):
        customer, created = User.objects.get_or_create(
            email=f'customer{i}@fidden.com',
            defaults={
                'name': f'Customer {i}',
                'role': 'customer',
                'is_verified': True,
            }
        )
        if created:
            customer.set_password('customer123')
            customer.save()
            print(f"  ✓ Created customer: {customer.email}")
        customers.append(customer)
    
    return owners, customers

def create_subscription_plans():
    """Create subscription plans"""
    print("\n💳 Creating subscription plans...")
    
    plans_data = [
        {
            'name': SubscriptionPlan.FOUNDATION,
            'monthly_price': Decimal('0.00'),
            'commission_rate': Decimal('15.00'),
            'marketplace_profile': True,
            'instant_booking_payments': True,
            'automated_reminders': True,
            'smart_rebooking_prompts': True,
            'deposit_customization': SubscriptionPlan.DEPOSIT_DEFAULT,
            'priority_marketplace_ranking': False,
            'advanced_calendar_tools': False,
            'auto_followups': False,
            'ai_assistant': SubscriptionPlan.AI_ADDON,
            'performance_analytics': SubscriptionPlan.PERF_NONE,
            'ghost_client_reengagement': False,
        },
        {
            'name': SubscriptionPlan.MOMENTUM,
            'monthly_price': Decimal('29.99'),
            'commission_rate': Decimal('10.00'),
            'marketplace_profile': True,
            'instant_booking_payments': True,
            'automated_reminders': True,
            'smart_rebooking_prompts': True,
            'deposit_customization': SubscriptionPlan.DEPOSIT_BASIC,
            'priority_marketplace_ranking': True,
            'advanced_calendar_tools': True,
            'auto_followups': True,
            'ai_assistant': SubscriptionPlan.AI_ADDON,
            'performance_analytics': SubscriptionPlan.PERF_BASIC,
            'ghost_client_reengagement': True,
        },
        {
            'name': SubscriptionPlan.ICON,
            'monthly_price': Decimal('99.99'),
            'commission_rate': Decimal('5.00'),
            'marketplace_profile': True,
            'instant_booking_payments': True,
            'automated_reminders': True,
            'smart_rebooking_prompts': True,
            'deposit_customization': SubscriptionPlan.DEPOSIT_ADVANCED,
            'priority_marketplace_ranking': True,
            'advanced_calendar_tools': True,
            'auto_followups': True,
            'ai_assistant': SubscriptionPlan.AI_INCLUDED,
            'performance_analytics': SubscriptionPlan.PERF_ADVANCED,
            'ghost_client_reengagement': True,
        },
    ]
    
    plans = []
    for plan_data in plans_data:
        plan, created = SubscriptionPlan.objects.get_or_create(
            name=plan_data['name'],
            defaults=plan_data
        )
        plans.append(plan)
        if created:
            print(f"  ✓ Created plan: {plan.name}")
        else:
            print(f"  → Plan already exists: {plan.name}")
    
    return plans

def create_shops(owners, plans):
    """Create shops"""
    print("\n🏪 Creating shops...")
    
    shops_data = [
        {
            'owner': owners['barber'],
            'name': "Bob's Barbershop",
            'niches': ['barber'],
            'address': '123 Main St, New York, NY',
            'capacity': 5,
        },
        {
            'owner': owners['tattoo_artist'],
            'name': 'Ink Haven Tattoo Studio',
            'niches': ['tattoo_artist'],
            'address': '456 Art Ave, Los Angeles, CA',
            'capacity': 3,
        },
        {
            'owner': owners['nail_tech'],
            'name': 'Glam Nails Salon',
            'niches': ['nail_tech', 'esthetician'],
            'address': '789 Beauty Blvd, Miami, FL',
            'capacity': 4,
        },
        {
            'owner': owners['fitness_trainer'],
            'name': 'FitLife Training Center',
            'niches': ['fitness_trainer'],
            'address': '321 Gym St, Austin, TX',
            'capacity': 10,
        },
    ]
    
    shops = {}
    for shop_data in shops_data:
        owner = shop_data.pop('owner')
        niches = shop_data.pop('niches')
        
        # Add required times
        from datetime import time as dt_time
        shop_data['start_at'] = dt_time(9, 0)   # 9:00 AM
        shop_data['close_at'] = dt_time(18, 0)  # 6:00 PM
        
        shop, created = Shop.objects.get_or_create(
            owner=owner,
            defaults=shop_data
        )
        if created or not shop.niches:
            shop.niches = niches
            shop.status = 'verified'
            shop.save()
            print(f"  ✓ Created shop: {shop.name} (niches: {niches})")
            
            # Create subscription
            ShopSubscription.objects.get_or_create(
                shop=shop,
                defaults={
                    'plan': plans[1],  # Use second plan (Momentum)
                    'status': 'active',
                }
            )
        
        shops[niches[0]] = shop
    
    return shops

def create_service_categories():
    """Create service categories"""
    print("\n🏷️  Creating service categories...")
    
    categories_data = [
        'Haircut', 'Nails', 'Tattoo', 'Skincare', 
        'Massage', 'Fitness', 'Makeup'
    ]
    
    categories = {}
    for name in categories_data:
        category, created = ServiceCategory.objects.get_or_create(
            name=name
        )
        if created:
            print(f"  ✓ Created category: {name}")
        categories[name.lower()] = category
    
    return categories

def create_services(shops, categories):
    """Create services for each shop"""
    print("\n🛠️  Creating services...")
    
    # Barber services
    barber_services = [
        ('Haircut', 25.00, 30, categories['haircut']),
        ('Beard Trim', 15.00, 15, categories['haircut']),
        ('Hot Shave', 30.00, 45, categories['haircut']),
    ]
    
    for title, price, duration, category in barber_services:
        Service.objects.get_or_create(
            shop=shops['barber'],
            title=title,
            defaults={
                'price': Decimal(str(price)),
                'duration': duration,
                'category': category,
                'capacity': 1,
            }
        )
    print(f"  ✓ Created {len(barber_services)} barber services")
    
    # Tattoo services
    tattoo_services = [
        ('Small Tattoo', 80.00, 60, categories['tattoo']),
        ('Medium Tattoo', 150.00, 120, categories['tattoo']),
        ('Large Tattoo (Session)', 300.00, 240, categories['tattoo']),
        ('Tattoo Touch-up', 50.00, 30, categories['tattoo']),
    ]
    
    for title, price, duration, category in tattoo_services:
        Service.objects.get_or_create(
            shop=shops['tattoo_artist'],
            title=title,
            defaults={
                'price': Decimal(str(price)),
                'duration': duration,
                'category': category,
                'capacity': 1,
                'requires_age_18_plus': True,
            }
        )
    print(f"  ✓ Created {len(tattoo_services)} tattoo services")
    
    # Nail services
    nail_services = [
        ('Manicure', 35.00, 45, categories['nails']),
        ('Pedicure', 45.00, 60, categories['nails']),
        ('Gel Nails', 60.00, 90, categories['nails']),
        ('Acrylic Full Set', 75.00, 120, categories['nails']),
    ]
    
    for title, price, duration, category in nail_services:
        Service.objects.get_or_create(
            shop=shops['nail_tech'],
            title=title,
            defaults={
                'price': Decimal(str(price)),
                'duration': duration,
                'category': category,
                'capacity': 1,
            }
        )
    print(f"  ✓ Created {len(nail_services)} nail services")

def create_tattoo_specific_data(shop, customers):
    """Create tattoo artist specific data"""
    print("\n🖋️  Creating tattoo artist data...")
    
    # Portfolio items
    portfolio_data = [
        {
            'title': 'Dragon Sleeve',
            'description': 'Full sleeve Japanese dragon in color',
            'tags': ['dragon', 'japanese', 'color', 'sleeve'],
        },
        {
            'title': 'Portrait Realism',
            'description': 'Realistic portrait of family member',
            'tags': ['portrait', 'realism', 'black-gray'],
        },
        {
            'title': 'Geometric Pattern',
            'description': 'Sacred geometry mandala design',
            'tags': ['geometric', 'mandala', 'linework'],
        },
    ]
    
    for data in portfolio_data:
        PortfolioItem.objects.get_or_create(
            shop=shop,
            title=data['title'],
            defaults={
                'description': data['description'],
                'tags': data['tags'],
            }
        )
    print(f"  ✓ Created {len(portfolio_data)} portfolio items")
    
    # Design requests
    design_requests_data = [
        {
            'user': customers[0],
            'description': 'Dragon wrapping around forearm',
            'placement': 'Left Forearm',
            'size_approx': '8x6 inches',
            'status': 'pending',
        },
        {
            'user': customers[1],
            'description': 'Phoenix rising from ashes on back',
            'placement': 'Upper Back',
            'size_approx': '12x10 inches',
            'status': 'approved',
        },
    ]
    
    for data in design_requests_data:
        user = data.pop('user')
        DesignRequest.objects.get_or_create(
            shop=shop,
            user=user,
            defaults=data
        )
    print(f"  ✓ Created {len(design_requests_data)} design requests")
    
    # Consent form template
    ConsentFormTemplate.objects.get_or_create(
        shop=shop,
        title='General Tattoo Waiver',
        defaults={
            'content': 'I acknowledge that tattoos are permanent and understand the risks...',
            'is_default': True,
        }
    )
    print("  ✓ Created consent form template")
    
    # ID verification requests
    id_verifications_data = [
        {
            'user': customers[0],
            'status': 'pending_upload',
        },
        {
            'user': customers[1],
            'status': 'under_review',
        },
    ]
    
    for data in id_verifications_data:
        user = data.pop('user')
        IDVerificationRequest.objects.get_or_create(
            shop=shop,
            user=user,
            defaults=data
        )
    print(f"  ✓ Created {len(id_verifications_data)} ID verification requests")

def main():
    """Main seed function"""
    print("=" * 70)
    print("🌱 SEEDING DATABASE")
    print("=" * 70)
    
    # Create all data
    owners, customers = create_users()
    plans = create_subscription_plans()
    shops = create_shops(owners, plans)
    categories = create_service_categories()
    create_services(shops, categories)
    
    # Create tattoo-specific data
    if 'tattoo_artist' in shops:
        create_tattoo_specific_data(shops['tattoo_artist'], customers)
    
    print("\n" + "=" * 70)
    print("✅ DATABASE SEEDING COMPLETE!")
    print("=" * 70)
    print("\n📝 Test Credentials:")
    print("\nAdmin:")
    print("  Email: admin@fidden.com")
    print("  Password: admin123")
    print("\nShop Owners:")
    print("  Barber: barbershop@fidden.com / owner123")
    print("  Tattoo: tattoo@fidden.com / owner123")
    print("  Nails: nails@fidden.com / owner123")
    print("  Fitness: fitness@fidden.com / owner123")
    print("\nCustomers:")
    print("  customer1@fidden.com through customer5@fidden.com / customer123")
    print("\n")

if __name__ == '__main__':
    main()
