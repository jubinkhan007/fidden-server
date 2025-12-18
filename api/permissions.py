from rest_framework import permissions

class IsOwnerAndOwnerRole(permissions.BasePermission):
    """
    Permission class for shop owners.
    - User must be authenticated
    - User must have role='owner'
    - For object-level: user must own the object (obj.owner or obj.shop.owner)
    """
    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
        if getattr(request.user, 'role', None) != 'owner':
            return False
        
        # Check direct owner (Shop model)
        if hasattr(obj, 'owner'):
            return obj.owner == request.user
        
        # Check nested shop.owner (ClientSkinProfile, TreatmentNote, etc.)
        if hasattr(obj, 'shop') and hasattr(obj.shop, 'owner'):
            return obj.shop.owner == request.user
        
        return False

    def has_permission(self, request, view):
        # All requests: must be authenticated owner
        return (
            request.user.is_authenticated and 
            getattr(request.user, 'role', None) == 'owner'
        )


class IsOwnerRole(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and getattr(request.user, 'role', None) == 'owner'
