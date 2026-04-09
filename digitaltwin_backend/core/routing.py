from django.urls import re_path
from . import consumers
from .consumers.command_consumer import CommandLifecycleConsumer
from .consumers.telemetry_consumers import TelemetryConsumer


websocket_urlpatterns = [
    re_path(r'ws/telemetry/$', TelemetryConsumer.as_asgi()),
    re_path(r'ws/commands/$', CommandLifecycleConsumer.as_asgi()),
]