"""Sign in with Apple: identity token verification, and token revocation for
account deletion. https://developer.apple.com/documentation/sign_in_with_apple"""

import logging
import time

import httpx
import jwt
from django.conf import settings

logger = logging.getLogger(__name__)

APPLE_ISSUER = "https://appleid.apple.com"
_jwks_client = jwt.PyJWKClient(f"{APPLE_ISSUER}/auth/keys", cache_keys=True)


class AppleAuthError(Exception):
    pass


def verify_identity_token(identity_token):
    """Check the identity token the app got from Apple and return its claims."""
    if not settings.APPLE_BUNDLE_ID:
        raise AppleAuthError("APPLE_BUNDLE_ID is not configured.")
    try:
        key = _jwks_client.get_signing_key_from_jwt(identity_token)
        return jwt.decode(
            identity_token,
            key.key,
            algorithms=["RS256"],
            audience=settings.APPLE_BUNDLE_ID,
            issuer=APPLE_ISSUER,
        )
    except jwt.PyJWTError as exc:
        raise AppleAuthError(f"Invalid Apple identity token: {exc}") from exc


def revocation_configured():
    return bool(
        settings.APPLE_TEAM_ID and settings.APPLE_KEY_ID and settings.APPLE_PRIVATE_KEY
    )


def _client_secret():
    now = int(time.time())
    return jwt.encode(
        {
            "iss": settings.APPLE_TEAM_ID,
            "iat": now,
            "exp": now + 300,
            "aud": APPLE_ISSUER,
            "sub": settings.APPLE_BUNDLE_ID,
        },
        settings.APPLE_PRIVATE_KEY,
        algorithm="ES256",
        headers={"kid": settings.APPLE_KEY_ID},
    )


def exchange_authorization_code(code):
    """Swap the one-time authorization code for a refresh token, which we keep
    only so we can revoke it later. Returns "" if not configured or on failure."""
    if not (code and revocation_configured()):
        return ""
    try:
        response = httpx.post(
            f"{APPLE_ISSUER}/auth/token",
            data={
                "client_id": settings.APPLE_BUNDLE_ID,
                "client_secret": _client_secret(),
                "code": code,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        response.raise_for_status()
        return response.json().get("refresh_token", "")
    except httpx.HTTPError:
        logger.exception("Apple authorization code exchange failed")
        return ""


def revoke_refresh_token(refresh_token):
    """Best effort: account deletion must not fail because Apple is down."""
    if not (refresh_token and revocation_configured()):
        return
    try:
        httpx.post(
            f"{APPLE_ISSUER}/auth/revoke",
            data={
                "client_id": settings.APPLE_BUNDLE_ID,
                "client_secret": _client_secret(),
                "token": refresh_token,
                "token_type_hint": "refresh_token",
            },
            timeout=10,
        ).raise_for_status()
    except httpx.HTTPError:
        logger.exception("Apple token revocation failed")
