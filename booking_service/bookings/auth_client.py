import jwt
from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed

class StatelessJWTAuthentication:
    @staticmethod
    def authenticate(request):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            raise AuthenticationFailed("Missing or invalid Authorization header")

        token = auth_header.split(' ')[1]
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
            return payload.get('user_id')
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed("Access token has expired")
        except jwt.InvalidTokenError:
            raise AuthenticationFailed("Invalid authorization token")