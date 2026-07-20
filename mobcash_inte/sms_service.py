import logging
import re

import requests

from accounts.models import User
from mobcash_inte.models import Setting

logger = logging.getLogger(__name__)


def normalize_sms_phone(phone: str) -> str:
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    return f"+{digits}" if digits else ""


def is_sms_enabled() -> bool:
    setting = Setting.objects.first()
    return bool(setting and setting.use_sms)


def _get_user_sms_phone(user) -> str:
    phone = getattr(user, "phone", None) or ""
    return normalize_sms_phone(phone)


def send_sms_message(to_phone: str, message: str) -> dict:
    from payment import CONNECT_PRO_BASE_URL, connect_pro_token

    if not is_sms_enabled():
        return {"success": False, "error": "sms_disabled"}

    to_phone = normalize_sms_phone(to_phone)
    if not to_phone:
        return {"success": False, "error": "invalid_phone"}

    token = connect_pro_token()
    if not token:
        return {"success": False, "error": "connect_auth_failed"}

    url = f"{CONNECT_PRO_BASE_URL}/api/payments/outbound-sms/"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {"to_phone": to_phone, "message": message}
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        if response.status_code in (200, 201):
            return {"success": True, "data": response.json()}
        return {
            "success": False,
            "error": response.text,
            "status": response.status_code,
        }
    except Exception as e:
        logger.error(f"send_sms_message error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def send_sms_to_user(user, title: str, content: str) -> dict:
    if not isinstance(user, User):
        return {"success": False, "error": "not_a_user"}
    if not is_sms_enabled():
        return {"success": False, "error": "sms_disabled"}

    phone = _get_user_sms_phone(user)
    if not phone:
        return {"success": False, "error": "no_phone"}
    if not getattr(user, "sms_verified", False):
        return {"success": False, "error": "sms_not_verified"}

    message = f"{title}\n\n{content}" if title else content
    return send_sms_message(phone, message)
