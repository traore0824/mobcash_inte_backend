import logging
import os

import requests

from accounts.models import User
from mobcash_inte.models import Setting

logger = logging.getLogger("mobcash_inte_backend.transactions")

DEFAULT_TELEGRAM_WEBHOOK_URL = "https://api.turaincash.com/auth/telegram-webhook"


def normalize_telegram_username(value: str) -> str:
    if not value:
        return ""
    username = value.strip()
    if "t.me/" in username:
        username = username.split("t.me/")[-1].split("?")[0].split("/")[0]
    return username.lstrip("@").lower()


def _get_setting():
    return Setting.objects.first()


def get_bot_token() -> str:
    """Token du bot (Setting), fallback env TOKEN_BOT."""
    setting = _get_setting()
    if setting and getattr(setting, "telegram_bot_token", None):
        return setting.telegram_bot_token.strip()
    return (os.getenv("TOKEN_BOT") or "").strip()


def is_telegram_enabled() -> bool:
    setting = _get_setting()
    return bool(setting and setting.use_telegram and get_bot_token())


def get_bot_username() -> str:
    setting = _get_setting()
    if setting and setting.telegram_bot_username:
        return normalize_telegram_username(setting.telegram_bot_username)
    return normalize_telegram_username(os.getenv("TELEGRAM_BOT_USERNAME", ""))


def get_telegram_link(user_id) -> str:
    bot_username = get_bot_username()
    if not bot_username:
        return ""
    return f"https://t.me/{bot_username}?start=link_{user_id}"


def _bot_api(method: str, params: dict = None) -> dict:
    bot_token = get_bot_token()
    if not bot_token:
        return {"ok": False, "error": "telegram_bot_not_configured"}
    url = f"https://api.telegram.org/bot{bot_token}/{method}"
    try:
        response = requests.get(url, params=params or {}, timeout=15)
        return response.json()
    except Exception as e:
        logger.error(f"telegram api {method} error: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}


def _bot_api_post(method: str, params: dict = None) -> dict:
    bot_token = get_bot_token()
    if not bot_token:
        return {"ok": False, "error": "telegram_bot_not_configured"}
    url = f"https://api.telegram.org/bot{bot_token}/{method}"
    try:
        response = requests.post(url, data=params or {}, timeout=15)
        return response.json()
    except Exception as e:
        logger.error(f"telegram api POST {method} error: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}


def get_telegram_webhook_info() -> dict:
    if not get_bot_token():
        return {"ok": False, "error": "telegram_bot_not_configured"}
    return _bot_api("getWebhookInfo")


def configure_telegram_webhook(webhook_url: str = None) -> dict:
    if not is_telegram_enabled():
        return {"ok": False, "error": "telegram_disabled"}
    url = (webhook_url or DEFAULT_TELEGRAM_WEBHOOK_URL).strip()
    return _bot_api_post("setWebhook", {"url": url})


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

    bot_token = get_bot_token()
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

    from mobcash_inte.helpers import html_to_plain_text

    plain_content = html_to_plain_text(content)
    plain_title = html_to_plain_text(title) if title else ""
    text = f"*{plain_title}*\n\n{plain_content}" if plain_title else plain_content
    return send_telegram_message(user.user_telegram_chat_id, text)
