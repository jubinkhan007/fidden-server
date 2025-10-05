from rest_framework import permissions

class IsOwnerAndOwnerRole(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return (
            request.user.is_authenticated and
            getattr(request.user, 'role', None) == 'owner' and
            obj.owner == request.user
        )

    def has_permission(self, request, view):
        if request.method == 'POST':
            return (
                request.user.is_authenticated and
                getattr(request.user, 'role', None) == 'owner' and
                not hasattr(request.user, 'shop')
            )
        return request.user.is_authenticated and getattr(request.user, 'role', None) == 'owner'


class IsOwnerRole(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and getattr(request.user, 'role', None) == 'owner'
