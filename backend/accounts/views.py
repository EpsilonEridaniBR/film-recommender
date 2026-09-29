import uuid

from django.contrib.auth import get_user_model
from django.db import transaction
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from . import apple
from .serializers import AppleSignInSerializer, MeSerializer

User = get_user_model()


class AppleSignInView(APIView):
    """Exchange a Sign in with Apple identity token for API tokens, creating
    the account on first sign-in. New accounts have no display name yet
    (`user.profile_complete` is false); set one with PATCH /me/."""

    permission_classes = [permissions.AllowAny]

    @extend_schema(
        request=AppleSignInSerializer,
        responses=inline_serializer(
            "AppleSignInResponse",
            {
                "access": serializers.CharField(),
                "refresh": serializers.CharField(),
                "user": MeSerializer(),
                "created": serializers.BooleanField(),
            },
        ),
    )
    def post(self, request):
        data = AppleSignInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            claims = apple.verify_identity_token(data.validated_data["identity_token"])
        except apple.AppleAuthError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)

        with transaction.atomic():
            user, created = User.objects.get_or_create(
                apple_sub=claims["sub"],
                # Django needs a unique username; it's internal and never shown.
                defaults={"username": uuid.uuid4().hex},
            )
            if created:
                user.set_unusable_password()
                user.save()
        if not user.is_active:
            return Response(
                {"detail": "This account is disabled."},
                status=status.HTTP_403_FORBIDDEN,
            )

        refresh_token = apple.exchange_authorization_code(
            data.validated_data.get("authorization_code")
        )
        if refresh_token:
            user.apple_refresh_token = refresh_token
            user.save(update_fields=["apple_refresh_token"])

        tokens = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(tokens.access_token),
                "refresh": str(tokens),
                "user": MeSerializer(user).data,
                "created": created,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class MeView(generics.RetrieveUpdateDestroyAPIView):
    """The signed-in user's profile. PATCH to set the display name; DELETE to
    delete the account (edits stay in the history without a name)."""

    serializer_class = MeSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "patch", "delete"]

    def get_object(self):
        return self.request.user

    def perform_destroy(self, user):
        apple.revoke_refresh_token(user.apple_refresh_token)
        user.delete()
