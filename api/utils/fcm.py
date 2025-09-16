import json
import os
import tempfile
import traceback
from typing import Any, Dict, Optional
from django.conf import settings
from pyfcm import FCMNotification
from pyfcm.errors import InvalidDataError
from api.models import Notification
import firebase_admin
from firebase_admin import credentials

# -------------------------------
# Initialize FCM service
# -------------------------------
def get_fcm_service() -> Optional[FCMNotification]:
    svc = getattr(settings, "FCM_SERVICE_ACCOUNT_FILE", None)

    if svc:
        try:
            if isinstance(svc, str) and os.path.exists(svc):
                return FCMNotification(service_account_file=svc)
            info = json.loads(svc) if isinstance(svc, str) else dict(svc)
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                json.dump(info, f)
                path = f.name
            return FCMNotification(service_account_file=path)
        except Exception as e:
            print("Failed to load FCM service account from settings:", e)

    try:
        service_account_json_str = os.environ.get("FCM_SERVICE_ACCOUNT_JSON")
        if service_account_json_str:
            info = json.loads(service_account_json_str)
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                json.dump(info, f)
                temp_path = f.name
            cred = credentials.Certificate(temp_path)
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            return FCMNotification(service_account_file=temp_path)
    except Exception as e:
        print("Failed to load FCM service account from env:", e)
        traceback.print_exc()

    print("FCM service not configured. Skipping push.")
    return None


push_service: Optional[FCMNotification] = get_fcm_service()

# -------------------------------
# Helpers
# -------------------------------
def _stringify(d: Optional[Dict[str, Any]]) -> Dict[str, str]:
    src = d or {}
    return {str(k): "" if v is None else str(v) for k, v in src.items()}


def _android_config() -> Dict[str, Any]:
    return {
        "priority": "HIGH",
        "notification": {
            "channel_id": "fidden_messages",
            "sound": "default",
            "click_action": "FLUTTER_NOTIFICATION_CLICK",
        },
    }


def _apns_config(title: str, body: str) -> Dict[str, Any]:
    return {
        "headers": {"apns-push-type": "alert", "apns-priority": "10"},
        "payload": {
            "aps": {
                "alert": {"title": title, "body": body},  # 👈 include title + body for iOS
                "sound": "default",
                "badge": 1,
            }
        },
    }


def _is_valid_fcm_token(token: str) -> bool:
    return token and len(token) > 50


# -------------------------------
# Sending push notifications
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
    if not push_service:
        if debug:
            print("FCM not configured, skipping push.")
        return

    tokens = [
        d.fcm_token
        for d in user.devices.all()
        if getattr(d, "fcm_token", None) and _is_valid_fcm_token(d.fcm_token)
    ]

    if not tokens:
        if debug:
            print(f"No valid FCM tokens for user {user.id}")
        return

    payload_data = _stringify(data)
    payload_data.setdefault("title", title)
    payload_data.setdefault("body", message)

    android_cfg = _android_config()
    apns_cfg = _apns_config(title, message)

    notification_block = {
        "title": title,
        "body": message,
    }

    for token in tokens:
        try:
            result = push_service.notify(
                fcm_token=token,
                data_payload=payload_data,
                notification=notification_block,   # 👈 REQUIRED for iOS + Android
                android_config=android_cfg,
                apns_config=apns_cfg,
                fcm_options={"analytics_label": "chat"},
                dry_run=dry_run,
                timeout=120,
            )
            if debug:
                print(f"FCM sent to {token}:", json.dumps(result, indent=2, ensure_ascii=False))
        except InvalidDataError:
            print(f"Invalid FCM token {token}, removing from DB")
            user.devices.filter(fcm_token=token).update(fcm_token="")
        except Exception as e:
            print(f"Failed sending to token {token}: {e}")
            traceback.print_exc()


def notify_user(
    user,
    message: str,
    notification_type: str = "chat",
    data: Optional[Dict[str, Any]] = None,
    *,
    debug: bool = False,
    dry_run: bool = False,
) -> None:
    Notification.objects.create(
        recipient=user,
        message=message,
        notification_type=notification_type,
        data=data or {},
    )
    send_push_notification(user, "New Notification", message, data, debug=debug, dry_run=dry_run)
