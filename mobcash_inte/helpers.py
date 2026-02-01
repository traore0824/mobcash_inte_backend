import logging
import os
import requests
from accounts.models import AppName, TelegramUser, User
from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from logger import LoggerService
from mobcash_inte.mobcash_service import BetApp
from mobcash_inte.models import BotMessage, Notification
from mobcash_inte.serializers import NotificationSerializer
from google.oauth2 import service_account
from fcm_django.models import FCMDevice
import google.auth.transport.requests
from dotenv import load_dotenv
import time
import secrets
import string

load_dotenv()


def get_access_token():
    credentials = service_account.Credentials.from_service_account_file(
        "mobcash.json", scopes=["https://www.googleapis.com/auth/firebase.messaging"]
    )
    request = google.auth.transport.requests.Request()
    credentials.refresh(request)
    return credentials.token


def call_api(fcm_token, title, body, message_data=None, image_url=None, priority=None):
    url = f"https://fcm.googleapis.com/v1/projects/{os.getenv('FIREBASE_PROJECT_ID', 'turaincash-57c48')}/messages:send"
    headers = {
        "Authorization": f"Bearer {get_access_token()}",
        "Content-Type": "application/json",
    }

    # Notification visuelle
    notification = {"title": title, "body": body}
    if image_url:
        notification["image"] = image_url

    payload = {
        "message": {
            "token": fcm_token,
            "notification": notification,
            "data": message_data or {},
            "android": {
                "priority": "HIGH",
                "notification": {
                    "channel_id": os.getenv("NOTIFICATION_CHANNEL"),
                    "sound": "default",
                },
            },
        }
    }

    try:
        LoggerService.i(f"POST {url} data={payload}")
        response = requests.post(url, headers=headers, json=payload)
        LoggerService.i(f"Response: {response.status_code} {response.text}")
        return response.json()
    except Exception as e:
        LoggerService.e(f"Error during POST {url}: {str(e)}")
        return str(e)


# def call_api(fcm_token, title, body, priority="normal", message_data=None):
#     url = f"https://fcm.googleapis.com/v1/projects/{os.getenv('FIREBASE_PROJECT_ID', 'turaincash-57c48')}/messages:send"
#     headers = {
#         "Authorization": f"Bearer {get_access_token()}",
#         "Content-Type": "application/json; UTF-8",
#     }
#     data = {
#         "message": {
#             "token": fcm_token,
#             "notification": {"title": title, "body": body},
#             "data": message_data or {},
#             "android": {"priority": priority},
#             "apns": {
#                 "headers": {"apns-priority": "10" if priority == "high" else "5"},
#             },
#             "webpush": {
#                 "headers": {"Urgency": priority.lower()},
#             },
#         }
#     }
#     response = requests.post(url=url, headers=headers, json=data, timeout=10)
#     return response.json()


def send_push_noti(user: User, title, body, data=None):
    devices = FCMDevice.objects.filter(user=user)[:3]
    for device in devices:
        connect_pro_logger = logging.getLogger("mobcash_inte_backend.transactions")
        response = call_api(
            device.registration_id, title=title, body=body, message_data=data
        )
        connect_pro_logger.info(f"send notification response 111111111111111 {response}")
        return response


@shared_task
def send_admin_notification(title: str, content: str, data=None, reference=None):
    users = User.objects.filter(is_staff=True)
    for user in users:
        send_notification(
            title=title, content=content, data=data, user=user, reference=reference
        )

connect_pro_logger = logging.getLogger("mobcash_inte_backend.transactions")
def send_notification(
    user: User | TelegramUser, title: str, content: str, data=None, reference=None
):

    try:
        if isinstance(user, TelegramUser) and user.telegram_user_id:
            # ✅ Notification via Telegram
            send_telegram_message(content=content, chat_id=user.telegram_user_id)
        elif isinstance(user, User):
            # ✅ Notification via push et base de données
            response = send_push_noti(user=user, title=title, body=content, data=data)
            connect_pro_logger.warning(
                f"send_notification: 1111111111111 ({response})"
            )
            notification = Notification.objects.create(
                title=title, content=content, user=user, reference=reference
            )
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"private_channel_{str(user.id)}",
                {
                    "type": "new_notification",
                    "data": NotificationSerializer(notification).data,
                },
            )
        else:
            connect_pro_logger.warning(
                f"send_notification: utilisateur inconnu ou non valide ({user})"
            )

    except Exception as e:
        connect_pro_logger.error(
            f"Erreur send_notification pour utilisateur {getattr(user, 'id', None)}: {str(e)}",
            exc_info=True,
        )


def send_telegram_message(content, chat_id=os.getenv("CHAT_ID")):
    bot_token = os.getenv("TOKEN_BOT")
    api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    data = {
        "chat_id": chat_id,
        "text": content,
    }
    try:

        response = requests.post(api_url, data=data)
        BotMessage.objects.create(content=content, chat=chat_id)
        return response.json()
    except:
        return None


def init_mobcash(app_name: AppName):
    bet_app = BetApp(
        hash=app_name.hash,
        cashdesk_id=app_name.cashdeskid,
        cashier_pass=app_name.cashierpass,
    )
    return bet_app


def generate_reference(prefix, rand_digits=3):
    millis = int(time.time() * 1_000)
    rnd = secrets.randbelow(10**rand_digits)
    return f"{prefix}{millis:013d}{rnd:0{rand_digits}d}"
