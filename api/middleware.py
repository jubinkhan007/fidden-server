from urllib.parse import parse_qs
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware

@database_sync_to_async
def get_user_from_token(token):
    # Import inside function to delay until apps are ready
    from rest_framework_simplejwt.authentication import JWTAuthentication
    from django.contrib.auth.models import AnonymousUser

    jwt_auth = JWTAuthentication()
    try:
        validated_token = jwt_auth.get_validated_token(token)
        user = jwt_auth.get_user(validated_token)
        return user
    except Exception:
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        from django.contrib.auth.models import AnonymousUser  # also delayed import

        query_string = parse_qs(scope["query_string"].decode())
        token = None

        if "token" in query_string:
            token = query_string["token"][0]

        if token:
            scope["user"] = await get_user_from_token(token)
        else:
            scope["user"] = AnonymousUser()

        return await super().__call__(scope, receive, send)
