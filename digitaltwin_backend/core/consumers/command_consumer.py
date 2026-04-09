import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)

class CommandLifecycleConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Dedicated group just for command lifecycles
        self.group_name = "command_updates"

        # Join the broadcast group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()
        logger.info("✅ [WEBSOCKET] Frontend connected to Command Lifecycle stream.")

    async def disconnect(self, close_code):
        # Leave the broadcast group
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )
        logger.info("❌ [WEBSOCKET] Frontend disconnected from Command stream.")

    async def command_update(self, event):
        # This method name MUST match the 'type' in the group_send call
        data = event.get("data", {})

        await self.send(text_data=json.dumps({
            "type": "command_lifecycle",
            "data": data
        }))