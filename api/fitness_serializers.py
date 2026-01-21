from rest_framework import serializers
from .models import FitnessPackage, WorkoutTemplate, NutritionPlan

class FitnessPackageSerializer(serializers.ModelSerializer):
    class Meta:
        model = FitnessPackage
        fields = '__all__'
        read_only_fields = ('created_at', 'shop')

class WorkoutTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkoutTemplate
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'shop')

class NutritionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = NutritionPlan
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'shop')
