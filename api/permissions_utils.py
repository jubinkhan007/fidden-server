# api/permissions_utils.py
from rest_framework import serializers
from subscriptions.models import SubscriptionPlan


class PlanBasedPermissionMixin:
    """
    Mixin to provide plan-based permission checking for serializers.
    """
    
    def get_user_plan(self, instance=None):
        """Get the user's current subscription plan from the shop."""
        shop = None
        
        # If instance is a Service, get the shop from service.shop
        if instance and hasattr(instance, 'shop'):
            shop = instance.shop
        # If instance is a Shop directly
        elif instance and hasattr(instance, 'subscription'):
            shop = instance
        else:
            # Try to get shop from request context
            request = self.context.get('request')
            if request and hasattr(request.user, 'shop'):
                shop = request.user.shop
            else:
                return SubscriptionPlan.FOUNDATION
        
        # Get subscription from the shop (not the service)
        if shop and hasattr(shop, 'subscription') and shop.subscription.is_active:
            return shop.subscription.plan.name
        return SubscriptionPlan.FOUNDATION
    
    def check_field_permission(self, field_name, plan_name, validated_data):
        """
        Check if a field can be modified based on the user's plan.
        Returns True if allowed, raises ValidationError if not.
        """
        if field_name not in validated_data:
            return True
            
        permissions = self.get_field_permissions()
        
        if field_name in permissions:
            allowed_plans = permissions[field_name]
            if plan_name not in allowed_plans:
                plan_names = {
                    SubscriptionPlan.FOUNDATION: 'Foundation',
                    SubscriptionPlan.MOMENTUM: 'Momentum', 
                    SubscriptionPlan.ICON: 'Icon'
                }
                current_plan_display = plan_names.get(plan_name, plan_name)
                required_plans = [plan_names.get(p, p) for p in allowed_plans]
                
                if len(required_plans) == 1:
                    required_text = f"'{required_plans[0]}'"
                else:
                    quoted_plans = [f"'{p}'" for p in required_plans]
                    required_text = f"one of: {', '.join(quoted_plans)}"
                
                raise serializers.ValidationError({
                    field_name: f"Your current '{current_plan_display}' plan does not allow modifying this field. "
                               f"Please upgrade to {required_text} plan."
                })
        
        return True
    
    def get_field_permissions(self):
        """
        Override this method to define field permissions.
        Returns a dict mapping field names to lists of allowed plans.
        """
        return {}
    
    def validate_plan_permissions(self, instance, validated_data):
        """Validate all fields against plan permissions."""
        plan_name = self.get_user_plan(instance)
        
        for field_name in validated_data.keys():
            self.check_field_permission(field_name, plan_name, validated_data)
        
        return validated_data


class ShopPermissionMixin(PlanBasedPermissionMixin):
    """Permission mixin specifically for Shop model."""
    
    def get_field_permissions(self):
        return {
            # Foundation: No modifications allowed for these fields
            'default_is_deposit_required': [SubscriptionPlan.MOMENTUM, SubscriptionPlan.ICON],
            'free_cancellation_hours': [SubscriptionPlan.ICON],
            'cancellation_fee_percentage': [SubscriptionPlan.ICON],
            'no_refund_hours': [SubscriptionPlan.ICON],
            
            # Momentum: Only deposit amount allowed
            'default_deposit_amount': [SubscriptionPlan.MOMENTUM, SubscriptionPlan.ICON],
            
            # Icon: All fields allowed (no restrictions needed)
        }


class ServicePermissionMixin(PlanBasedPermissionMixin):
    """
    Permission mixin for Service model.
    Note: Services inherit permissions from their Shop's subscription plan.
    """
    
    def get_field_permissions(self):
        return {
            # Foundation: No deposit modifications allowed
            'is_deposit_required': [SubscriptionPlan.MOMENTUM, SubscriptionPlan.ICON],
            'deposit_type': [SubscriptionPlan.MOMENTUM, SubscriptionPlan.ICON],
            'deposit_percentage': [SubscriptionPlan.MOMENTUM, SubscriptionPlan.ICON],
            
            # Momentum: Only deposit amount allowed
            'deposit_amount': [SubscriptionPlan.MOMENTUM, SubscriptionPlan.ICON],
            
            # Icon: All fields allowed (no restrictions needed)
        }


def get_modification_permissions(user):
    """
    Get a summary of what the user can modify based on their plan.
    Returns a dictionary with permission flags.
    """
    try:
        shop = user.shop
        if hasattr(shop, 'subscription') and shop.subscription.is_active:
            plan_name = shop.subscription.plan.name
        else:
            plan_name = SubscriptionPlan.FOUNDATION
    except:
        plan_name = SubscriptionPlan.FOUNDATION
    
    permissions = {
        'plan': plan_name,
        'can_modify_shop_deposit_settings': plan_name in [SubscriptionPlan.MOMENTUM, SubscriptionPlan.ICON],
        'can_modify_shop_deposit_amount': plan_name in [SubscriptionPlan.MOMENTUM, SubscriptionPlan.ICON],
        'can_modify_shop_cancellation_policy': plan_name == SubscriptionPlan.ICON,
        'can_modify_service_deposit_settings': plan_name in [SubscriptionPlan.MOMENTUM, SubscriptionPlan.ICON],
        'can_modify_service_deposit_amount': plan_name in [SubscriptionPlan.MOMENTUM, SubscriptionPlan.ICON],
        'can_modify_all_settings': plan_name == SubscriptionPlan.ICON,
    }
    
    return permissions