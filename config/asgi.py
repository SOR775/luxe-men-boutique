"""LUXE MEN — ASGI Application (WebSockets via Django Channels)"""
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')

django_asgi_app = get_asgi_application()

# Import after setup
from notifications.routing import websocket_urlpatterns
from support.routing import chat_websocket_urlpatterns

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AuthMiddlewareStack(
        URLRouter(
            websocket_urlpatterns + chat_websocket_urlpatterns
        )
    ),
})
