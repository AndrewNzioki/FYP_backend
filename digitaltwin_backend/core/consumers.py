import json
from channels.generic.websocket import AsyncWebsocketConsumer

class TelemetryConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.group_name = "telemetry_updates"

        # Join the broadcast group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()
        print("[WEBSOCKET] Client connected to live telemetry.")

    async def disconnect(self, close_code):
        # Leave the broadcast group
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )
        print("[WEBSOCKET] Client disconnected.")

    # This method catches events sent to the group and pushes them to the browser
    async def send_telemetry(self, event):
        data = event["data"]
        await self.send(text_data=json.dumps({
            "type": "telemetry_update",
            "data": data
        }))