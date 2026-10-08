from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import serializers

from .names import clean_display_name


class AppleSignInSerializer(serializers.Serializer):
    identity_token = serializers.CharField()
    authorization_code = serializers.CharField(required=False, allow_blank=True)


class DevSignInSerializer(serializers.Serializer):
    display_name = serializers.CharField()

    def validate_display_name(self, value):
        return clean_display_name(value)


class MeSerializer(serializers.ModelSerializer):
    profile_complete = serializers.SerializerMethodField()
    pending_edits = serializers.SerializerMethodField()
    max_pending_edits = serializers.SerializerMethodField()

    class Meta:
        model = get_user_model()
        fields = [
            "display_name",
            "profile_complete",
            "can_moderate",
            "date_joined",
            "pending_edits",
            "max_pending_edits",
        ]
        read_only_fields = ["can_moderate", "date_joined"]

    def get_profile_complete(self, user) -> bool:
        """False until the user has chosen a display name; the app should ask
        for one (pre-filled with the first name Apple shares) before letting
        them propose or vote."""
        return bool(user.display_name)

    def get_pending_edits(self, user) -> int:
        return user.suggestion_edits.filter(status="pending").count()

    def get_max_pending_edits(self, user) -> int:
        return settings.MAX_PENDING_EDITS_PER_USER

    def validate_display_name(self, value):
        return clean_display_name(value)
