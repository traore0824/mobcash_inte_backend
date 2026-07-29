"""Proxy chatbot My Customer — réutilise openwa_token (X-API-Key)."""

from __future__ import annotations

import logging
import os

import requests

from mobcash_inte.models import Setting
from mobcash_inte.whatsapp_service import get_whatsapp_base_url

logger = logging.getLogger("mobcash_inte_backend.transactions")
# connect, read — le LLM My Customer peut dépasser 60–90 s
REQUEST_TIMEOUT = (15, 120)


def get_chatbot_message_url() -> str:
    """
    MYCUSTOMER_WHATSAPP_BASE_URL se termine souvent par /api/v1.
    Le chatbot est sur /api/sdk/message/.
    """
    override = (os.getenv("MYCUSTOMER_CHATBOT_MESSAGE_URL") or "").strip()
    if override:
        return override.rstrip("/")
    wa = get_whatsapp_base_url().rstrip("/")
    if wa.endswith("/v1"):
        return f"{wa[:-3]}/sdk/message/"
    if wa.endswith("/api"):
        return f"{wa}/sdk/message/"
    return f"{wa}/sdk/message/"


def is_chatbot_enabled() -> bool:
    setting = Setting.objects.first()
    return bool(setting and setting.use_chatbot and setting.openwa_token)


def send_chatbot_message(
    *,
    message: str,
    customer_external_id: str,
    customer_name: str = "",
    conversation_id: str | None = None,
    page_key: str = "",
    route: str = "",
    screen_title: str = "",
    audio_bytes: bytes | None = None,
    audio_name: str = "message-vocal.ogg",
    audio_content_type: str = "audio/ogg",
) -> tuple[dict, int]:
    setting = Setting.objects.first()
    if not setting or not setting.use_chatbot:
        return {"detail": "Chatbot désactivé.", "code": "chatbot_disabled"}, 403
    if not setting.openwa_token:
        return {"detail": "Clé My Customer manquante.", "code": "missing_api_key"}, 503

    payload = {
        "message": (message or "").strip(),
        "customer_external_id": (customer_external_id or "anonymous").strip()
        or "anonymous",
    }
    if customer_name.strip():
        payload["customer_name"] = customer_name.strip()[:120]
    if conversation_id:
        payload["conversation_id"] = conversation_id
    if page_key:
        payload["page_key"] = page_key
    if route:
        payload["route"] = route
    if screen_title:
        payload["screen_title"] = screen_title

    if not payload["message"] and not audio_bytes:
        return {"detail": "message est requis."}, 400

    url = get_chatbot_message_url()
    headers = {"X-API-Key": setting.openwa_token}
    logger.info("Chatbot message → %s customer=%s", url, payload["customer_external_id"])
    try:
        if audio_bytes:
            response = requests.post(
                url,
                headers=headers,
                data=payload,
                files={
                    "audio": (
                        audio_name or "message-vocal.ogg",
                        audio_bytes,
                        audio_content_type or "audio/ogg",
                    )
                },
                timeout=REQUEST_TIMEOUT,
            )
        else:
            response = requests.post(
                url,
                headers={**headers, "Content-Type": "application/json"},
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
    except requests.RequestException as exc:
        logger.exception("Chatbot request failed: %s", exc)
        return {"detail": "Service chatbot indisponible.", "code": "upstream_error"}, 502

    try:
        body = response.json()
    except Exception:
        body = {"detail": "Réponse chatbot invalide.", "code": "invalid_upstream"}

    if response.status_code >= 400:
        logger.warning(
            "Chatbot ← status=%s body=%s",
            response.status_code,
            str(body)[:400],
        )
        detail = body.get("detail") if isinstance(body, dict) else None
        if (
            not isinstance(detail, str)
            or detail.lstrip().startswith("<!")
            or "Server Error" in str(detail)
        ):
            body = {
                "detail": "Le service chatbot a renvoyé une erreur. Réessayez.",
                "code": "upstream_error",
                "upstream_status": response.status_code,
            }
        out_status = 502 if response.status_code >= 500 else response.status_code
        return body if isinstance(body, dict) else {"detail": str(body)}, out_status

    return body if isinstance(body, dict) else {"detail": str(body)}, response.status_code
