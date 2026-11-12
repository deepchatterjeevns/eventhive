from dataclasses import dataclass
import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed


@dataclass
class AuthenticatedTokenUser:
    id: int

    @property
    def is_authenticated(self) -> bool:
        return True


class StatelessJWTAuthentication(BaseAuthentication):
    """
    Stateless DRF authentication backend that verifies HMAC-SHA256 JWTs
    signed by auth_service using JWT_SIGNING_KEY (with fallback to SECRET_KEY).
    Enforces expiration ('exp') and rejects refresh tokens ('token_type' != 'access').
    """

    def authenticate(self, request):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None

        token = auth_header.split(" ", 1)[1].strip()
        signing_key = getattr(settings, "JWT_SIGNING_KEY", settings.SECRET_KEY)

        try:
            payload = jwt.decode(
                token,
                signing_key,
                algorithms=["HS256"],
                options={"require": ["exp", "user_id"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise AuthenticationFailed("Access token has expired.") from exc
        except jwt.InvalidTokenError as exc:
            raise AuthenticationFailed("Invalid authorization token.") from exc

        token_type = payload.get("token_type", "access")
        if token_type != "access":
            raise AuthenticationFailed("Invalid token type: access token required.")

        return (AuthenticatedTokenUser(id=int(payload["user_id"])), payload)
