# api/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import ChatThread, Message
from .serializers import MessageSerializer
from .utils.fcm import notify_user

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]
        if user.is_anonymous:
            await self.close()
        else:
            self.room_group_name = f"user_{user.id}"
            await self.channel_layer.group_add(self.room_group_name, self.channel_name)
            await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get("action")
        if action == "send_message":
            await self.handle_send_message(data)
        elif action == "mark_read":
            await self.handle_mark_read(data)

    @database_sync_to_async
    def create_message(self, sender, thread_id, content):
        thread = ChatThread.objects.get(id=thread_id)
        message = Message.objects.create(thread=thread, sender=sender, content=content)
        # Notify recipient
        recipient = thread.shop.owner if sender != thread.shop.owner else thread.user
        notify_user(recipient, f"New message from {sender.email}", data={"thread_id": thread.id})
        return MessageSerializer(message).data, recipient.id

    async def handle_send_message(self, data):
        user = self.scope["user"]
        thread_id = data["thread_id"]
        content = data["content"]
        message_data, recipient_id = await self.create_message(user, thread_id, content)

        # Send to recipient
        await self.channel_layer.group_send(
            f"user_{recipient_id}",
            {"type": "chat_message", "message": message_data},
        )

        # Send back to sender
        await self.send(text_data=json.dumps({"type": "chat_message", "message": message_data}))

    @database_sync_to_async
    def mark_messages_as_read(self, thread_id, user):
        return Message.objects.filter(thread_id=thread_id, is_read=False).exclude(sender=user).update(is_read=True)

    async def handle_mark_read(self, data):
        thread_id = data["thread_id"]
        user = self.scope["user"]
        await self.mark_messages_as_read(thread_id, user)
        await self.send(text_data=json.dumps({"type": "mark_read", "thread_id": thread_id}))

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event))
