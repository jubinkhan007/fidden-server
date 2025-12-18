from rest_framework import permissions

class IsOwnerAndOwnerRole(permissions.BasePermission):
    """
    Permission class for shop owners.
    - User must be authenticated
    - User must have role='owner'
    - For object-level: user must own the object's shop
    """
    def has_object_permission(self, request, view, obj):
        return (
            request.user.is_authenticated and
            getattr(request.user, 'role', None) == 'owner' and
            obj.owner == request.user
        )

    def has_permission(self, request, view):
        # All requests: must be authenticated owner
        return (
            request.user.is_authenticated and 
            getattr(request.user, 'role', None) == 'owner'
        )


class IsOwnerRole(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and getattr(request.user, 'role', None) == 'owner'
