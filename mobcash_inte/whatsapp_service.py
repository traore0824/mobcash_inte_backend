import logging
import re

import requests

from accounts.models import User
from mobcash_inte.models import Setting

OPENWA_BASE_URL = "https://wa.manoschange.com"
logger = logging.getLogger("mobcash_inte_backend.transactions")


def normalize_whatsapp_phone(phone: str) -> str:
    if not phone:
        return ""
    return re.sub(r"\D", "", phone)


def is_whatsapp_enabled() -> bool:
    setting = Setting.objects.first()
    return bool(
        setting
        and setting.use_whatsapp
        and setting.openwa_session_id
        and setting.openwa_token
    )


def _get_whatsapp_setting():
    setting = Setting.objects.first()
    if not setting or not setting.use_whatsapp:
        return None
    if not setting.openwa_session_id or not setting.openwa_token:
        return None
    return setting


def validate_whatsapp_phone(phone: str) -> dict:
    setting = _get_whatsapp_setting()
    if not setting:
        return {"valid": False, "exists": False, "error": "whatsapp_disabled"}

    phone = normalize_whatsapp_phone(phone)
    if not phone:
        return {"valid": False, "exists": False, "error": "invalid_phone"}

    url = (
        f"{OPENWA_BASE_URL}/api/sessions/{setting.openwa_session_id}"
        f"/contacts/check/{phone}"
    )
    headers = {
        "X-API-Key": setting.openwa_token,
        "Content-Type": "application/json",
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        return {
            "valid": True,
            "exists": data.get("exists", False),
            "whatsapp_id": data.get("whatsappId"),
            "number": data.get("number", phone),
        }
    except Exception as e:
        logger.error(f"validate_whatsapp_phone error: {e}", exc_info=True)
        return {"valid": False, "exists": False, "error": str(e)}


def send_whatsapp_message(phone: str, text: str, chat_id: str = None) -> dict:
    setting = _get_whatsapp_setting()
    if not setting:
        return {"success": False, "error": "whatsapp_disabled"}

    phone = normalize_whatsapp_phone(phone)
    if not chat_id:
        check = validate_whatsapp_phone(phone)
        if not check.get("exists"):
            return {"success": False, "error": "number_not_on_whatsapp"}
        chat_id = check.get("whatsapp_id") or f"{phone}@c.us"

    url = (
        f"{OPENWA_BASE_URL}/api/sessions/{setting.openwa_session_id}"
        f"/messages/send-text"
    )
    headers = {
        "X-API-Key": setting.openwa_token,
        "Content-Type": "application/json",
    }
    payload = {"chatId": chat_id, "text": text}
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code in (200, 201):
            return {"success": True, "data": response.json()}
        return {
            "success": False,
            "error": response.text,
            "status": response.status_code,
        }
    except Exception as e:
        logger.error(f"send_whatsapp_message error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def send_whatsapp_to_user(user, title: str, content: str) -> dict:
    if not isinstance(user, User):
        return {"success": False, "error": "not_a_user"}
    if not is_whatsapp_enabled():
        return {"success": False, "error": "whatsapp_disabled"}
    if not user.user_whatsapp_phone:
        return {"success": False, "error": "no_whatsapp_phone"}
    if not getattr(user, "whatsapp_verified", False):
        return {"success": False, "error": "whatsapp_not_verified"}

    text = f"*{title}*\n\n{content}" if title else content
    return send_whatsapp_message(user.user_whatsapp_phone, text)
