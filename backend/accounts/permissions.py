from rest_framework.permissions import BasePermission


class IsModerator(BasePermission):
    """Any signed-in user who has chosen a display name and hasn't been banned."""

    message = "Sign in and choose a display name to suggest and review edits."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user and user.is_authenticated and user.can_moderate and user.display_name
        )
