# api/utils/fcm.py
from pyfcm import FCMNotification
from django.conf import settings
from api.models import Notification
import os
import json
import tempfile

# Initialize FCM service
def get_fcm_service():
    """Initialize FCM service with proper configuration"""
    # Check if service account file is provided
    if hasattr(settings, 'FCM_SERVICE_ACCOUNT_FILE') and settings.FCM_SERVICE_ACCOUNT_FILE:
        if os.path.exists(settings.FCM_SERVICE_ACCOUNT_FILE):
            return FCMNotification(service_account_file=settings.FCM_SERVICE_ACCOUNT_FILE)
        else:
            # If file doesn't exist, treat the value as JSON content
            try:
                service_account_info = json.loads(settings.FCM_SERVICE_ACCOUNT_FILE)
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                    json.dump(service_account_info, f)
                    temp_file_path = f.name
                return FCMNotification(service_account_file=temp_file_path)
            except (json.JSONDecodeError, KeyError):
                pass
    
    # Check if server key is provided
    fcm_key = settings.FCM_SERVER_KEY
    if fcm_key:
        # Check if it's a service account key (JSON string) or server key
        if fcm_key.startswith('{') or 'client_email' in fcm_key:
            # It's a service account key, create a temporary file
            try:
                # Parse the JSON to validate it
                service_account_info = json.loads(fcm_key)
                
                # Create a temporary file with the service account key
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                    json.dump(service_account_info, f)
                    temp_file_path = f.name
                
                # Initialize FCM with the service account file
                return FCMNotification(service_account_file=temp_file_path)
            except (json.JSONDecodeError, KeyError):
                # If it's not valid JSON, treat it as a server key
                return FCMNotification(fcm_key)
        else:
            # It's a legacy server key
            return FCMNotification(fcm_key)
    
    # If no configuration is provided, return None to handle gracefully
    return None

push_service = get_fcm_service()

def send_push_notification(user, title, message, data=None):
    if not push_service:
        print("FCM service not configured. Skipping push notification.")
        return
    
    tokens = [d.device_token for d in user.devices.all()]
    if tokens:
        # Send notification to each device token individually
        for token in tokens:
            try:
                push_service.notify(
                    fcm_token=token,
                    data_payload={
                        "title": title,
                        "body": message,
                        **(data or {})
                    }
                )
            except Exception as e:
                print(f"Failed to send push notification to token {token}: {e}")

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