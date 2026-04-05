import json
from channels.generic.websocket import AsyncWebsocketConsumer


class TelemetryConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # FATAL FLAW 1 FIXED: Group name now exactly matches handlers.py
        self.group_name = "telemetry_group"

        # Join the broadcast group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()
        print("✅ [WEBSOCKET] Browser connected to live SCADA telemetry.")

    async def disconnect(self, close_code):
        # Leave the broadcast group
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )
        print("❌ [WEBSOCKET] Browser disconnected.")

    # FATAL FLAW 2 FIXED: Method name exactly matches the "type" sent by handlers.py
    async def telemetry_update(self, event):
        # FATAL FLAW 3 FIXED: Stop filtering the dict. Pass the raw C++ payload straight to the UI.
        data = event.get("data", {})

        await self.send(text_data=json.dumps({
            "type": "telemetry_update",
            "data": data
        }))