from channels.generic.websocket import AsyncWebsocketConsumer
import json


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        if self.scope['user'].is_anonymous:
            await self.close()
            return

        self.group_name = f'notifications_{self.scope["user"].pk}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        # Client may send pings or subscribe requests in future.
        pass

    async def notification_message(self, event):
        payload = event.get('payload', {})
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'payload': payload,
        }))
