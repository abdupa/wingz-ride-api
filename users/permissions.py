from rest_framework.permissions import BasePermission


class IsAdminRole(BasePermission):
    """
    Allows only authenticated users whose role is 'admin'.

    Deliberately not DRF's built-in IsAdminUser. That one checks user.is_staff,
    which is a Django admin-site concept and a field this project's User model
    does not have -- the names are close enough to be genuinely dangerous.
    """

    message = "Only users with the 'admin' role may call this API."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.role == user.Role.ADMIN
        )
