import logging
import os
import re

import requests

from accounts.models import User
from mobcash_inte.models import Setting

# Sur le même serveur que My Customer, préfère une URL interne via env
# pour éviter le timeout hairpin NAT (appel public vers soi-même) :
#   MYCUSTOMER_WHATSAPP_BASE_URL=http://127.0.0.1:PORT/api/v1
DEFAULT_MYCUSTOMER_WHATSAPP_BASE_URL = "https://api.mycustomer.manoschange.com/api/v1"
REQUEST_TIMEOUT = (10, 60)  # (connect, read)
logger = logging.getLogger("mobcash_inte_backend.transactions")


def get_whatsapp_base_url() -> str:
    return (
        os.getenv("MYCUSTOMER_WHATSAPP_BASE_URL") or DEFAULT_MYCUSTOMER_WHATSAPP_BASE_URL
    ).rstrip("/")


MYCUSTOMER_WHATSAPP_BASE_URL = get_whatsapp_base_url()


def normalize_whatsapp_phone(phone: str) -> str:
    """Indicatif pays sans '+' (ex. 22955187395)."""
    if not phone:
        return ""
    return re.sub(r"\D", "", phone)


def is_whatsapp_enabled() -> bool:
    setting = Setting.objects.first()
    return bool(setting and setting.use_whatsapp and setting.openwa_token)


def _get_whatsapp_setting():
    setting = Setting.objects.first()
    if not setting or not setting.use_whatsapp:
        return None
    if not setting.openwa_token:
        return None
    return setting


def _api_headers(setting) -> dict:
    return {
        "X-API-Key": setting.openwa_token,
        "Content-Type": "application/json",
    }


def _get_user_whatsapp_phone(user) -> str:
    return normalize_whatsapp_phone(
        getattr(user, "user_whatsapp_phone", None)
        or getattr(user, "whatsapp", None)
        or ""
    )


def validate_whatsapp_phone(phone: str) -> dict:
    """Vérifie si un numéro a WhatsApp via POST /messages/check/."""
    setting = _get_whatsapp_setting()
    if not setting:
        return {"valid": False, "exists": False, "error": "whatsapp_disabled"}

    phone = normalize_whatsapp_phone(phone)
    if not phone:
        return {"valid": False, "exists": False, "error": "invalid_phone"}

    base = get_whatsapp_base_url()
    url = f"{base}/messages/check/"
    logger.info("WhatsApp check → %s phone=%s", url, phone)
    try:
        response = requests.post(
            url,
            headers=_api_headers(setting),
            json={"phone": phone},
            timeout=REQUEST_TIMEOUT,
        )
        logger.info(
            "WhatsApp check ← status=%s body=%s",
            response.status_code,
            (response.text or "")[:500],
        )
        if response.status_code == 401:
            return {"valid": False, "exists": False, "error": "invalid_api_key"}
        if response.status_code == 502:
            return {"valid": False, "exists": False, "error": "whatsapp_line_not_ready"}

        response.raise_for_status()
        data = response.json() if response.content else {}
        exists = bool(data.get("exists", False))
        return {
            "valid": True,
            "exists": exists,
            "whatsapp_id": data.get("whatsapp_id"),
            "number": data.get("phone", phone),
            "success": data.get("success", True),
        }
    except requests.exceptions.Timeout as e:
        logger.warning("validate_whatsapp_phone timeout on %s: %s", url, e)
        return {
            "valid": False,
            "exists": False,
            "error": "timeout",
            "detail": str(e),
            "url": url,
            "hint": (
                "Si My Customer tourne sur le même serveur, définis "
                "MYCUSTOMER_WHATSAPP_BASE_URL=http://127.0.0.1:<PORT>/api/v1"
            ),
        }
    except Exception as e:
        logger.error("validate_whatsapp_phone error: %s", e)
        return {"valid": False, "exists": False, "error": str(e), "url": url}


def send_whatsapp_message(
    phone: str,
    text: str,
    chat_id: str = None,
    check_whatsapp: bool = False,
) -> dict:
    """
    Envoie un message via POST /messages/send/
    chat_id est ignoré (compatibilité ancienne API).
    """
    setting = _get_whatsapp_setting()
    if not setting:
        return {"success": False, "error": "whatsapp_disabled"}

    phone = normalize_whatsapp_phone(phone)
    if not phone:
        return {"success": False, "error": "invalid_phone"}
    if not text:
        return {"success": False, "error": "empty_message"}

    if len(text) > 4096:
        text = text[:4096]

    base = get_whatsapp_base_url()
    url = f"{base}/messages/send/"
    payload = {
        "to": phone,
        "text": text,
        "check_whatsapp": check_whatsapp,
    }
    logger.info(
        "WhatsApp send → %s to=%s check_whatsapp=%s",
        url,
        phone,
        check_whatsapp,
    )
    try:
        response = requests.post(
            url,
            headers=_api_headers(setting),
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        data = {}
        try:
            data = response.json() if response.content else {}
        except Exception:
            data = {"raw": response.text}

        logger.info(
            "WhatsApp send ← status=%s body=%s",
            response.status_code,
            (response.text or "")[:500],
        )

        if response.status_code in (200, 201):
            return {
                "success": True,
                "data": data,
                "message_id": data.get("message_id"),
                "status": data.get("status"),
            }

        error_code = data.get("code") or data.get("error") or response.text
        if response.status_code == 400 and (
            error_code == "number_not_on_whatsapp"
            or "number_not_on_whatsapp" in str(data).lower()
            or "number_not_on_whatsapp" in str(response.text).lower()
        ):
            return {"success": False, "error": "number_not_on_whatsapp", "status": 400}
        if response.status_code == 401:
            return {"success": False, "error": "invalid_api_key", "status": 401}
        if response.status_code == 429:
            return {"success": False, "error": "daily_limit_reached", "status": 429}
        if response.status_code == 502:
            return {"success": False, "error": "whatsapp_line_not_ready", "status": 502}

        return {
            "success": False,
            "error": error_code or response.text,
            "status": response.status_code,
            "data": data,
        }
    except requests.exceptions.Timeout as e:
        logger.warning("send_whatsapp_message timeout on %s: %s", url, e)
        return {
            "success": False,
            "error": "timeout",
            "detail": str(e),
            "url": url,
            "hint": (
                "Si My Customer tourne sur le même serveur, définis "
                "MYCUSTOMER_WHATSAPP_BASE_URL=http://127.0.0.1:<PORT>/api/v1"
            ),
        }
    except Exception as e:
        logger.error("send_whatsapp_message error: %s", e)
        return {"success": False, "error": str(e), "url": url}


def _platform_labels() -> list[str]:
    """Noms de plateformes (AppName) à retirer des messages WhatsApp uniquement."""
    from accounts.models import AppName

    labels: set[str] = set()
    for app in AppName.objects.all().only("name"):
        if app.name and str(app.name).strip():
            labels.add(str(app.name).strip())
        public_name = getattr(app, "public_name", None)
        if public_name and str(public_name).strip():
            labels.add(str(public_name).strip())
    labels.update({"plateforme", "l'application", "Application inconnue"})
    return sorted(labels, key=len, reverse=True)


def strip_platform_names_for_whatsapp(text: str) -> str:
    """
    Retire le nom de plateforme des textes WhatsApp.
    Push / in-app / Telegram / SMS gardent le contenu d'origine.
    """
    if not text:
        return text

    labels = _platform_labels()
    if not labels:
        return text

    names_alt = "|".join(re.escape(label) for label in labels)
    patterns = [
        (rf"\s+sur votre compte\s+(?:{names_alt})\b", ""),
        (rf"\s+de votre compte\s+(?:{names_alt})\b", ""),
        (rf"\s+depuis\s+(?:{names_alt})\b", ""),
        (rf"\s+sur\s+(?:{names_alt})\b", ""),
        (rf"\s+de\s+(?:{names_alt})\b", ""),
        (rf"(?:{names_alt})\s+Message\s*:", "Message:"),
        (rf"(?:{names_alt})\s+Message\b", "Message"),
        (rf"(demande de (?:dépôt|retrait)(?:\s+de)?)\s+(?:{names_alt})\b", r"\1"),
        (rf"\s+(?:{names_alt})\b", ""),
    ]
    result = text
    for pattern, repl in patterns:
        result = re.sub(pattern, repl, result, flags=re.IGNORECASE)

    result = re.sub(r"[ \t]{2,}", " ", result)
    result = re.sub(r"\s+\.", ".", result)
    result = re.sub(r"\.\.+", ".", result)
    return result.strip()


def send_whatsapp_to_user(user, title: str, content: str) -> dict:
    if not isinstance(user, User):
        return {"success": False, "error": "not_a_user"}
    if not is_whatsapp_enabled():
        return {"success": False, "error": "whatsapp_disabled"}

    phone = _get_user_whatsapp_phone(user)
    # Fallback: téléphone profil si WhatsApp lié mais numéro WA vide
    if not phone:
        phone = normalize_whatsapp_phone(getattr(user, "phone", None) or "")

    if not phone:
        # Incohérence fréquente: whatsapp_verified=True sans numéro en DB
        if getattr(user, "whatsapp_verified", False):
            try:
                user.whatsapp_verified = False
                user.save(update_fields=["whatsapp_verified"])
            except Exception:
                pass
        return {"success": False, "error": "no_whatsapp_phone"}
    if not getattr(user, "whatsapp_verified", False):
        return {"success": False, "error": "whatsapp_not_verified"}

    # Import local pour éviter le cycle helpers ↔ whatsapp_service
    from mobcash_inte.helpers import html_to_plain_text

    plain_content = strip_platform_names_for_whatsapp(html_to_plain_text(content))
    plain_title = html_to_plain_text(title) if title else ""
    text = f"*{plain_title}*\n\n{plain_content}" if plain_title else plain_content
    return send_whatsapp_message(phone, text)
