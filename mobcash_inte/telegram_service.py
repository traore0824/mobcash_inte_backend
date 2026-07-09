import logging
import os

import requests

from accounts.models import User
from mobcash_inte.models import Setting

logger = logging.getLogger("mobcash_inte_backend.transactions")


def normalize_telegram_username(value: str) -> str:
    if not value:
        return ""
    username = value.strip()
    if "t.me/" in username:
        username = username.split("t.me/")[-1].split("?")[0].split("/")[0]
    return username.lstrip("@").lower()


def is_telegram_enabled() -> bool:
    setting = Setting.objects.first()
    return bool(setting and setting.use_telegram and os.getenv("TOKEN_BOT"))


def get_bot_username() -> str:
    setting = Setting.objects.first()
    if setting and setting.telegram_bot_username:
        return normalize_telegram_username(setting.telegram_bot_username)
    return normalize_telegram_username(os.getenv("TELEGRAM_BOT_USERNAME", ""))


def get_telegram_link(user_id) -> str:
    bot_username = get_bot_username()
    if not bot_username:
        return ""
    return f"https://t.me/{bot_username}?start=link_{user_id}"


def _bot_api(method: str, params: dict = None) -> dict:
    bot_token = os.getenv("TOKEN_BOT")
    if not bot_token:
        return {"ok": False, "error": "telegram_bot_not_configured"}
    url = f"https://api.telegram.org/bot{bot_token}/{method}"
    try:
        response = requests.get(url, params=params or {}, timeout=15)
        return response.json()
    except Exception as e:
        logger.error(f"telegram api {method} error: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}


def validate_telegram_username(username: str) -> dict:
    if not is_telegram_enabled():
        return {"valid": False, "exists": False, "error": "telegram_disabled"}

    username = normalize_telegram_username(username)
    if not username:
        return {"valid": False, "exists": False, "error": "invalid_username"}

    data = _bot_api("getChat", {"chat_id": f"@{username}"})
    if not data.get("ok"):
        return {
            "valid": False,
            "exists": False,
            "error": "user_must_start_bot",
            "username": username,
        }

    chat = data.get("result", {})
    return {
        "valid": True,
        "exists": True,
        "username": chat.get("username") or username,
        "chat_id": str(chat.get("id")),
    }


def send_telegram_message(chat_id: str, text: str) -> dict:
    if not is_telegram_enabled():
        return {"success": False, "error": "telegram_disabled"}

    bot_token = os.getenv("TOKEN_BOT")
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        response = requests.post(
            url,
            data={"chat_id": chat_id, "text": text},
            timeout=15,
        )
        data = response.json()
        if data.get("ok"):
            return {"success": True, "data": data}
        return {"success": False, "error": data.get("description", response.text)}
    except Exception as e:
        logger.error(f"send_telegram_message error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def link_telegram_to_user(user: User, chat_id: str, username: str = None) -> User:
    user.user_telegram_chat_id = str(chat_id)
    if username:
        user.user_telegram_username = normalize_telegram_username(username)
    user.telegram_verified = True
    user.save(
        update_fields=[
            "user_telegram_chat_id",
            "user_telegram_username",
            "telegram_verified",
        ]
    )
    return user


def send_telegram_to_user(user, title: str, content: str) -> dict:
    if not isinstance(user, User):
        return {"success": False, "error": "not_a_user"}
    if not is_telegram_enabled():
        return {"success": False, "error": "telegram_disabled"}
    if not user.telegram_verified or not user.user_telegram_chat_id:
        return {"success": False, "error": "telegram_not_verified"}

    text = f"*{title}*\n\n{content}" if title else content
    return send_telegram_message(user.user_telegram_chat_id, text)
