# api/utils/fcm.py
import json, os, tempfile, traceback
from typing import Any, Dict, Optional, List
from django.conf import settings
from api.models import Notification
import firebase_admin
from firebase_admin import credentials, messaging


def _init_firebase() -> None:
    if firebase_admin._apps:
        return
    try:
        svc = getattr(settings, "FCM_SERVICE_ACCOUNT_JSON", None)

        if not svc:
            print("FCM_SERVICE_ACCOUNT_JSON not found in settings.")
            return

        print("🔍 Attempting to initialize Firebase with config...")
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(svc, f)
            temp_path = f.name

        try:
            cred = credentials.Certificate(temp_path)
            firebase_admin.initialize_app(cred)
            print("✅ Firebase initialized successfully!")
        finally:
            try:
                os.unlink(temp_path)  # Clean up temp file
            except:
                pass

    except Exception as e:
        print(f"❌ Failed to initialize Firebase: {e}")
        traceback.print_exc()

def _stringify(d: Optional[Dict[str, Any]]) -> Dict[str, str]:
    src = d or {}
    return {str(k): "" if v is None else str(v) for k, v in src.items()}

def _android_cfg() -> messaging.AndroidConfig:
    return messaging.AndroidConfig(
        priority="high",
        notification=messaging.AndroidNotification(
            channel_id="fidden_messages",
            sound="default",
            click_action="FLUTTER_NOTIFICATION_CLICK",
        ),
    )

def _apns_cfg(title: str, body: str) -> messaging.APNSConfig:
    return messaging.APNSConfig(
        ##old setup##
        # headers={"apns-push-type": "alert", "apns-priority": "10", "apns-push-type": "background","apns-priority": "5"},
        ##new header###
        headers={ "apns-push-type": "alert", "apns-priority": "10"},
        payload=messaging.APNSPayload(
            aps=messaging.Aps(
                alert=messaging.ApsAlert(title=title, body=body),
                sound="default",
                badge=1,
                # content_available=True,
            )

        ),
    )

def _valid(token: str) -> bool:
    return bool(token) and len(token) > 50


def send_push_notification(
        user,
        title: str,
        message: str,
        data: Optional[Dict[str, Any]] = None,
        *,
        debug: bool = False,
        dry_run: bool = False,
) -> None:
    _init_firebase()
    if not firebase_admin._apps:
        if debug:
            print("Firebase Admin not configured; skipping push.")
        return

    print(f"DEBUG: Sending notification - Title: '{title}', Message: '{message}'")

    # Ensure we have a valid message
    if not message or not isinstance(message, str):
        message = "New notification"

    # Ensure we have a valid title
    if not title or not isinstance(title, str):
        title = "New Message"

    tokens: List[str] = [d.fcm_token for d in user.devices.all() if _valid(getattr(d, "fcm_token", ""))]
    if not tokens:
        if debug:
            print(f"No valid FCM tokens for user {user.id}")
        return

    # FCM requires string values in data
    data_map = _stringify(data or {})

    # Create a notification with both title and body
    notification = messaging.Notification(
        title=title,
        body=message,
    )

    android = _android_cfg()
    apns = _apns_cfg(title, message)

    try:
        # Send to each token individually
        for token in tokens:
            fcm_message = messaging.Message(
                token=token,
                notification=notification,
                data=data_map,
                android=android,
                apns=apns,
            )
            try:
                response = messaging.send(fcm_message, dry_run=dry_run)
                print(f"Successfully sent message: {response}")
            except Exception as e:
                print(f"Error sending message to token {token}: {e}")
                # Optionally, remove invalid tokens from the database
                # user.devices.filter(fcm_token=token).delete()

    except Exception as e:
        print(f"Error in send_push_notification: {e}")
        traceback.print_exc()


##########this is the old one ###########

# def notify_user(
#     user,
#     message: str,
#     notification_type: str = "chat",
#     data: Optional[Dict[str, Any]] = None,
#     *,
#     debug: bool = False,
#     dry_run: bool = False,
# ) -> None:
#     Notification.objects.create(
#         recipient=user,
#         message=message,
#         notification_type=notification_type,
#         data=data or {},
#     )
#     # Give a meaningful title by type
#     title = {
#         "chat": "New Message",
#         "booking": "New Booking",
#         "booking_reminder": "Booking Reminder",
#     }.get(notification_type, "Notification")
#
#     send_push_notification(
#         user=user,
#         title=title,
#         message=message,
#         data=data,
#         debug=debug,
#         dry_run=dry_run,
#     )


#########this is the new one ##########
def notify_user(
        user,
        message: str,
        notification_type: str = "chat",
        data: Optional[Dict[str, Any]] = None,
        *,
        debug: bool = False,
        dry_run: bool = False,
):
    # Create notification in database
    notification = Notification.objects.create(
        recipient=user,
        message=message,
        notification_type=notification_type,
        data=data or {},
    )

    # For iOS background notifications, ensure data payload is included
    if data is None:
        data = {}

    # Add notification_id to data for deep linking
    data["notification_id"] = str(notification.id)
    data["type"] = notification_type
    data["click_action"] = "FLUTTER_NOTIFICATION_CLICK"  # For Flutter

    # Send push notification
    send_push_notification(
        user=user,
        title="New Message" if notification_type == "chat" else "Notification",
        message=message,
        data=data,
        debug=debug,
        dry_run=dry_run,
    )
    return notification
