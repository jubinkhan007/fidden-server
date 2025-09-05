# api/utils/fcm.py
from pyfcm import FCMNotification
from django.conf import settings
from api.models import  Notification

push_service = FCMNotification(settings.FCM_SERVER_KEY)

def send_push_notification(user, title, message, data=None):
    tokens = [d.device_token for d in user.devices.all()]
    if tokens:
        push_service.notify_multiple_devices(
            registration_ids=tokens,
            message_title=title,
            message_body=message,
            data_message=data or {}
        )

def notify_user(user, message, notification_type="chat", data=None):
    # Save to DB
    Notification.objects.create(
        recipient=user,
        message=message,
        notification_type=notification_type,
        data=data or {}
    )
    # Send FCM
    send_push_notification(user, "New Notification", message, data)