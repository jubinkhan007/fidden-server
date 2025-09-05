import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fidden.settings")

# Initialize Django ASGI application first
django_asgi_app = get_asgi_application()

# Import middleware after Django apps are ready
from api.middleware import JWTAuthMiddleware

# Delayed import of routing to avoid AppRegistryNotReady
from importlib import import_module
api_routing = import_module("api.routing")

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddleware(
        URLRouter(api_routing.websocket_urlpatterns)
    ),
})
