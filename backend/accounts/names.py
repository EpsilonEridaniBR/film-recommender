from rest_framework import serializers

DISPLAY_NAME_MAX_LENGTH = 50


def clean_display_name(value):
    value = " ".join(value.split())
    if not value:
        raise serializers.ValidationError("Enter a display name.")
    if len(value) > DISPLAY_NAME_MAX_LENGTH:
        raise serializers.ValidationError(
            f"Display names can be at most {DISPLAY_NAME_MAX_LENGTH} characters."
        )
    return value
