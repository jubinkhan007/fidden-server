#!/usr/bin/env python
"""
Simple seed script to create a superuser for testing
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fidden.settings')
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

# Create superuser
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
    print(f"✅ Created admin user: admin@fidden.com / admin123")
else:
    print(f"→ Admin user already exists: admin@fidden.com")

print("\nYou can now:")
print("1. Access Django Admin: http://localhost:8000/admin/")
print("2. Create more users and data via admin panel")
print("3. Test Consultation API at /api/consultations/")
