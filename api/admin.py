from django.contrib import admin
from .models import Shop, Service, ServiceCategory

class ServiceInline(admin.TabularInline):
    model = Service
    extra = 1

@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'address', 'location', 'capacity')
    inlines = [ServiceInline]

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('title', 'shop', 'category', 'price', 'discount_price')
    list_filter = ('shop', 'category')

@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)
