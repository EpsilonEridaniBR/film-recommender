from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    # Stable Apple user identifier ("sub" claim) from Sign in with Apple.
    apple_sub = models.CharField(max_length=255, unique=True, null=True, blank=True)
    # Apple refresh token, kept only so it can be revoked when the account is
    # deleted (an App Store requirement).
    apple_refresh_token = models.TextField(blank=True)
    # The name users choose, shown on their suggestions and in the moderation queue.
    # Blank until they pick one after first sign-in.
    display_name = models.CharField(max_length=50, blank=True)
    # Every signed-in user can moderate; switch off to ban an abusive user.
    can_moderate = models.BooleanField(default=True)
