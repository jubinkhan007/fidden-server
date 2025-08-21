from rest_framework import serializers
from .models import Shop, Service, ServiceCategory


class ServiceCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceCategory
        fields = ['id', 'name']


class ServiceSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    category = serializers.PrimaryKeyRelatedField(queryset=ServiceCategory.objects.all())

    class Meta:
        model = Service
        fields = [
            'id', 'title', 'price', 'discount_price', 'description',
            'service_img', 'category', 'duration', 'capacity'
        ]
        read_only_fields = ('shop',)


class ShopSerializer(serializers.ModelSerializer):
    services = ServiceSerializer(many=True, required=False)
    owner_id = serializers.IntegerField(source='owner.id', read_only=True)

    class Meta:
        model = Shop
        fields = [
            'id', 'name', 'address', 'location', 'capacity', 'start_at',
            'close_at', 'about_us', 'shop_img', 'owner_id', 'services'
        ]
        read_only_fields = ('owner_id',)

    def create(self, validated_data):
        services_data = validated_data.pop('services', [])
        shop = Shop.objects.create(**validated_data)

        for service_data in services_data:
            Service.objects.create(shop=shop, **service_data)

        return shop

    def update(self, instance, validated_data):
        services_data = validated_data.pop('services', [])

        # Update shop fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        existing_services = {s.id: s for s in instance.services.all()}
        updated_service_ids = []

        for service_data in services_data:
            service_id = service_data.get('id', None)

            if service_id:
                # Update existing service
                service = existing_services.get(service_id)
                if not service:
                    raise serializers.ValidationError(f"Service with id {service_id} does not exist.")
                for attr, value in service_data.items():
                    if attr != 'id':
                        setattr(service, attr, value)
                service.save()
                updated_service_ids.append(service.id)
            else:
                # Create new service without affecting existing IDs
                new_service = Service.objects.create(shop=instance, **service_data)
                updated_service_ids.append(new_service.id)

        # Optional: remove services not in the payload
        for service in instance.services.all():
            if service.id not in updated_service_ids:
                service.delete()

        return instance
