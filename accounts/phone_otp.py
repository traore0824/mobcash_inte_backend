"""
OTP SMS téléphone (inscription + enregistrement numéro).
Envoi via Connect Pro outbound-sms (sms_service.send_sms_message).
Stockage cache Redis (TTL) — même logique que Connect/CENOF.
"""

from __future__ import annotations

import logging
import secrets
import string
from typing import Optional

from django.conf import settings
from django.core.cache import cache

from mobcash_inte.sms_service import is_sms_enabled, normalize_sms_phone, send_sms_message

logger = logging.getLogger(__name__)

OTP_TTL = 600  # 10 min
TOKEN_TTL = 900  # 15 min après vérif
RESEND_COOLDOWN = 60
OTP_LENGTH = 6

OTP_PREFIX = "phone_otp:"
TOKEN_PREFIX = "phone_verified:"
COOLDOWN_PREFIX = "phone_otp_cd:"

PURPOSE_REGISTRATION = "registration"
PURPOSE_SMS_PHONE = "sms_phone"
PURPOSE_USER_PHONE = "user_phone"
VALID_PURPOSES = {PURPOSE_REGISTRATION, PURPOSE_SMS_PHONE, PURPOSE_USER_PHONE}


def build_full_phone(phone: str, phone_indicative: str | None = None) -> str:
    raw = (phone or "").strip()
    indicative = (phone_indicative or "").strip()
    digits_phone = "".join(c for c in raw if c.isdigit())
    digits_ind = "".join(c for c in indicative if c.isdigit())

    if raw.startswith("+") or (digits_phone and len(digits_phone) >= 10 and not digits_ind):
        return normalize_sms_phone(raw)

    if digits_ind and digits_phone:
        # éviter double indicatif si le local commence déjà par l'indicatif
        if digits_phone.startswith(digits_ind):
            return normalize_sms_phone(digits_phone)
        return normalize_sms_phone(f"{digits_ind}{digits_phone}")

    return normalize_sms_phone(digits_phone or raw)


def _otp_key(phone: str, purpose: str) -> str:
    return f"{OTP_PREFIX}{purpose}:{phone}"


def _token_key(token: str) -> str:
    return f"{TOKEN_PREFIX}{token}"


def _cooldown_key(phone: str, purpose: str) -> str:
    return f"{COOLDOWN_PREFIX}{purpose}:{phone}"


def _generate_otp() -> str:
    if getattr(settings, "PHONE_OTP_TEST_MODE", False) or getattr(
        settings, "CONNECT_SMS_TEST_MODE", False
    ):
        return "123456"
    return "".join(secrets.choice(string.digits) for _ in range(OTP_LENGTH))


def _generate_token() -> str:
    return secrets.token_urlsafe(24)


def send_phone_otp(
    phone: str,
    purpose: str,
    phone_indicative: str | None = None,
    brand: str = "votre service",
) -> dict:
    purpose = (purpose or "").strip().lower()
    if purpose not in VALID_PURPOSES:
        return {"success": False, "error": "invalid_purpose", "details": "Purpose invalide"}

    full_phone = build_full_phone(phone, phone_indicative)
    if not full_phone or len(full_phone) < 8:
        return {"success": False, "error": "invalid_phone", "details": "Numéro invalide"}

    if not is_sms_enabled():
        return {"success": False, "error": "sms_disabled", "details": "SMS non activé"}

    if cache.get(_cooldown_key(full_phone, purpose)):
        return {
            "success": False,
            "error": "cooldown",
            "details": "Veuillez patienter avant de renvoyer un code.",
        }

    otp = _generate_otp()
    cache.set(_otp_key(full_phone, purpose), otp, timeout=OTP_TTL)
    cache.set(_cooldown_key(full_phone, purpose), "1", timeout=RESEND_COOLDOWN)

    message = (
        f"Votre code de verification {brand} est : {otp}. "
        f"Valable {OTP_TTL // 60} minutes."
    )
    result = send_sms_message(full_phone, message)
    if not result.get("success"):
        cache.delete(_otp_key(full_phone, purpose))
        cache.delete(_cooldown_key(full_phone, purpose))
        logger.warning("phone OTP SMS failed for %s: %s", full_phone, result)
        return {
            "success": False,
            "error": "sms_send_failed",
            "details": "Impossible d'envoyer le SMS.",
        }

    logger.info("phone OTP sent purpose=%s phone=%s", purpose, full_phone)
    return {
        "success": True,
        "phone": full_phone,
        "expires_in": OTP_TTL,
        "resend_in": RESEND_COOLDOWN,
    }


def verify_phone_otp(
    phone: str,
    code: str,
    purpose: str,
    phone_indicative: str | None = None,
) -> dict:
    purpose = (purpose or "").strip().lower()
    if purpose not in VALID_PURPOSES:
        return {"success": False, "error": "invalid_purpose", "details": "Purpose invalide"}

    full_phone = build_full_phone(phone, phone_indicative)
    pin = (code or "").strip()
    if not full_phone or not pin:
        return {"success": False, "error": "invalid_request", "details": "Téléphone ou code manquant"}

    saved = cache.get(_otp_key(full_phone, purpose))
    if saved is None:
        return {
            "success": False,
            "error": "otp_expired",
            "details": "Code expiré. Demandez-en un nouveau.",
        }
    if str(saved).strip() != pin:
        return {
            "success": False,
            "error": "otp_invalid",
            "details": "Code de vérification invalide",
        }

    cache.delete(_otp_key(full_phone, purpose))
    token = _generate_token()
    cache.set(
        _token_key(token),
        {"phone": full_phone, "purpose": purpose},
        timeout=TOKEN_TTL,
    )
    return {
        "success": True,
        "phone": full_phone,
        "phone_verification_token": token,
        "expires_in": TOKEN_TTL,
    }


def consume_phone_verification_token(
    token: Optional[str],
    phone: str,
    purpose: str,
    phone_indicative: str | None = None,
) -> bool:
    """Consomme le token (one-shot). True si valide pour ce téléphone + purpose."""
    if not token:
        return False
    purpose = (purpose or "").strip().lower()
    full_phone = build_full_phone(phone, phone_indicative)
    payload = cache.get(_token_key(token))
    if not isinstance(payload, dict):
        return False
    if payload.get("purpose") != purpose:
        return False
    if normalize_sms_phone(payload.get("phone") or "") != full_phone:
        return False
    cache.delete(_token_key(token))
    return True
