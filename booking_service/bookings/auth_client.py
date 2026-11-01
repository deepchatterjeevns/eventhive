import jwt
from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed


class AuthenticatedUser:
    """Lightweight stand-in for request.user used by stateless JWT auth."""

    def __init__(self, user_id):
        self.id = user_id
        self.user_id = user_id
        self.pk = user_id
        self.is_authenticated = True
        self.is_active = True
        self.is_anonymous = False

    def __str__(self):
        return f"User {self.user_id}"


class StatelessJWTAuthentication:
    @staticmethod
    def authenticate(request):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            raise AuthenticationFailed("Missing or invalid Authorization header")

        token = auth_header.split(' ')[1]
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed("Access token has expired")
        except jwt.InvalidTokenError:
            raise AuthenticationFailed("Invalid authorization token")

        user_id = payload.get('user_id')
        if user_id is None:
            raise AuthenticationFailed("Token does not contain a user_id")

        return AuthenticatedUser(user_id)