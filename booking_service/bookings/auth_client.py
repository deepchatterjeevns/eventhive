import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed


class AuthenticatedUser:
    """Lightweight stand-in for request.user used by stateless JWT auth.

    The booking service owns no user table, so the identity carried by the
    token is deliberately unmanaged: only what the JWT asserts is available.
    """

    def __init__(self, user_id):
        self.id = user_id
        self.user_id = user_id
        self.pk = user_id
        self.is_authenticated = True
        self.is_active = True
        self.is_anonymous = False

    def __str__(self):
        return f"User {self.user_id}"


class StatelessJWTAuthentication(BaseAuthentication):
    """Verifies Bearer tokens issued by the auth service.

    Both services must be configured with the same JWT_SIGNING_KEY, otherwise
    tokens signed by the auth service cannot be verified here.
    """

    keyword = "Bearer"

    def authenticate(self, request):
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            # Absence of credentials is not an error: public endpoints stay open
            # and permission classes decide whether the request may proceed.
            return None

        parts = auth_header.split()
        if len(parts) != 2 or parts[0] != self.keyword:
            raise AuthenticationFailed("Missing or malformed Authorization header")

        signing_key = getattr(settings, "JWT_SIGNING_KEY", settings.SECRET_KEY)
        try:
            payload = jwt.decode(
                parts[1],
                signing_key,
                algorithms=["HS256"],
                options={"require": ["exp"]},
            )
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed("Access token has expired")
        except jwt.InvalidTokenError:
            raise AuthenticationFailed("Invalid authorization token")

        user_id = payload.get("user_id")
        if user_id is None:
            raise AuthenticationFailed("Token does not contain a user_id")

        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            raise AuthenticationFailed("Token contains an invalid user_id")

        return AuthenticatedUser(user_id), parts[1]

    def authenticate_header(self, request):
        return self.keyword
