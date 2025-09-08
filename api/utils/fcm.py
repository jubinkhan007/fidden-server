# # api/utils/fcm.py
# from pyfcm import FCMNotification
# from django.conf import settings
# from api.models import Notification
# import os
# import json
# import tempfile
# import requests

# # Initialize FCM service
# def get_fcm_service():
#     """Initialize FCM service with proper configuration"""
#     # Preferred: explicit service account file path
#     if getattr(settings, 'FCM_SERVICE_ACCOUNT_FILE', None):
#         service_account_value = settings.FCM_SERVICE_ACCOUNT_FILE
#         if isinstance(service_account_value, str) and os.path.exists(service_account_value):
#             return FCMNotification(service_account_file=service_account_value)
#         # If not a path, maybe it's JSON content
#         try:
#             service_account_info = json.loads(service_account_value)
#             with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
#                 json.dump(service_account_info, f)
#                 temp_file_path = f.name
#             return FCMNotification(service_account_file=temp_file_path)
#         except (json.JSONDecodeError, TypeError, KeyError):
#             pass

#     # Fallback: allow JSON provided via FCM_SERVER_KEY only if it's actually a service account JSON
#     fcm_key = getattr(settings, 'FCM_SERVER_KEY', None)
#     if fcm_key and isinstance(fcm_key, str) and (fcm_key.strip().startswith('{')):
#         try:
#             service_account_info = json.loads(fcm_key)
#             with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
#                 json.dump(service_account_info, f)
#                 temp_file_path = f.name
#             return FCMNotification(service_account_file=temp_file_path)
#         except (json.JSONDecodeError, KeyError):
#             pass

#     # If no valid service account credentials found, disable FCM gracefully
#     return None

# push_service = get_fcm_service()

# def get_legacy_server_key():
#     """Return legacy FCM server key if configured"""
#     key = getattr(settings, 'FCM_SERVER_KEY', None)
#     # Only treat as legacy key if it's not JSON (to avoid misinterpreting service account JSON)
#     if isinstance(key, str) and not key.strip().startswith('{'):
#         return key.strip()
#     return None

# LEGACY_SERVER_KEY = get_legacy_server_key()

# def send_with_legacy_server_key(token, title, message, data=None):
#     """Send push via legacy HTTP API using server key."""
#     if not LEGACY_SERVER_KEY:
#         return
#     headers = {
#         'Authorization': f'key={LEGACY_SERVER_KEY}',
#         'Content-Type': 'application/json',
#     }
#     payload = {
#         'to': token,
#         'notification': {
#             'title': title,
#             'body': message,
#         },
#         'data': data or {},
#     }
#     resp = requests.post('https://fcm.googleapis.com/fcm/send', headers=headers, json=payload, timeout=20)
#     resp.raise_for_status()

# def send_push_notification(user, title, message, data=None):
#     if not push_service and not LEGACY_SERVER_KEY:
#         print("FCM service not configured (no service account or server key). Skipping push notification.")
#         return
    
#     tokens = [d.device_token for d in user.devices.all()]
#     if tokens:
#         # Send notification to each device token individually
#         for token in tokens:
#             try:
#                 if push_service:
#                     result = push_service.notify(
#                         fcm_token=token,
#                         notification_title=title,
#                         notification_body=message,
#                         data_payload=data or {}
#                     )
#                     print("result:", result)
#                 else:
#                     send_with_legacy_server_key(token, title, message, data)
#                     print("result: sent via legacy server key")
#             except Exception as e:
#                 print(f"Failed to send push notification to token {token}: {e}")

# def notify_user(user, message, notification_type="chat", data=None):
#     # Save to DB
#     Notification.objects.create(
#         recipient=user,
#         message=message,
#         notification_type=notification_type,
#         data=data or {}
#     )
#     # Send FCM
#     send_push_notification(user, "New Notification", message, data)


# api/utils/fcm.py
from __future__ import annotations
import json
import os
import tempfile
import traceback
from typing import Any, Dict, Optional
from django.conf import settings
from pyfcm import FCMNotification
from api.models import Notification
import firebase_admin
from firebase_admin import credentials

# -------------------------------
# FCM client (HTTP v1 only)
# -------------------------------
def get_fcm_service() -> Optional[FCMNotification]:
    """
    Initialize FCM using a Service Account JSON (path, JSON string, or env variable)
    - settings.FCM_SERVICE_ACCOUNT_FILE: absolute path OR JSON string
    - fallback: os.environ['FCM_SERVICE_ACCOUNT_JSON']
    """
    svc = getattr(settings, "FCM_SERVICE_ACCOUNT_FILE", None)

    # Try using FCM_SERVICE_ACCOUNT_FILE from settings
    if svc:
        try:
            # If it's a path on disk
            if isinstance(svc, str) and os.path.exists(svc):
                return FCMNotification(service_account_file=svc)

            # If it's JSON content
            info = json.loads(svc) if isinstance(svc, str) else dict(svc)
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                json.dump(info, f)
                path = f.name
            return FCMNotification(service_account_file=path)
        except Exception as e:
            print("Failed to load FCM service account from settings:", e)

    # Fallback: try environment variable
    try:
        service_account_json_str = os.environ.get("FCM_SERVICE_ACCOUNT_JSON")
        if service_account_json_str:
            info = json.loads(service_account_json_str)
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                json.dump(info, f)
                temp_path = f.name
            # Initialize Firebase Admin SDK (optional if using pyfcm)
            cred = credentials.Certificate(temp_path)
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            return FCMNotification(service_account_file=temp_path)
        else:
            print("FCM_SERVICE_ACCOUNT_JSON environment variable not set.")
    except Exception as e:
        print("Failed to load FCM service account from environment variable:", e)
        traceback.print_exc()

    print("FCM service not configured. Skipping push.")
    return None

push_service: Optional[FCMNotification] = get_fcm_service()

# -------------------------------
# Helpers
# -------------------------------
def _stringify(d: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """FCM data map must be strings."""
    src = d or {}
    return {str(k): ("" if v is None else str(v)) for k, v in src.items()}

def _android_config() -> Dict[str, Any]:
    return {
        "priority": "HIGH",
        "notification": {
            "channel_id": "fidden_messages",
            "sound": "default",
            "click_action": "FLUTTER_NOTIFICATION_CLICK",
        },
    }

def _apns_config() -> Dict[str, Any]:
    return {
        "headers": {
            "apns-push-type": "alert",
            "apns-priority": "10",
        },
        "payload": {
            "aps": {
                "alert": {},
                "sound": "default",
                "badge": 1,
            }
        },
    }

# -------------------------------
# Senders (HTTP v1 only)
# -------------------------------
def send_push_notification(
    user,
    title: str,
    message: str,
    data: Optional[Dict[str, Any]] = None,
    *,
    debug: bool = False,
    dry_run: bool = False,
) -> None:
    """
    Sends push notifications using FCM HTTP v1 only
    - title/body included in data_payload for Flutter
    """
    if not push_service:
        print("FCM service not configured. Skipping push.")
        return

    tokens = [d.device_token for d in user.devices.all() if getattr(d, "device_token", None)]
    if not tokens:
        return

    payload_data = _stringify(data)
    payload_data.setdefault("title", title)
    payload_data.setdefault("body", message)

    android_cfg = _android_config()
    apns_cfg = _apns_config()

    for token in tokens:
        try:
            result = push_service.notify(
                fcm_token=token,
                data_payload=payload_data,
                android_config=android_cfg,
                apns_config=apns_cfg,
                fcm_options={"analytics_label": "chat"},
                dry_run=dry_run,
                timeout=120,
            )
            if debug:
                print(f"\nFCM sent to token {token}:\n", json.dumps(result, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"Failed to send push notification to token {token}: {e}")
            traceback.print_exc()

def notify_user(
    user,
    message: str,
    notification_type: str = "chat",
    data: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Persist notification in DB + send FCM
    """
    Notification.objects.create(
        recipient=user,
        message=message,
        notification_type=notification_type,
        data=data or {},
    )
    send_push_notification(user, "New Notification", message, data)
