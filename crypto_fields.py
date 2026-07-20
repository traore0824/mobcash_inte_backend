"""
crypto_fields.py
================
Chiffrement Fernet pour les champs sensibles en DB.

Règle :
- en DB  → toujours chiffré
- en mémoire / avant envoi API → toujours déchiffré
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


def _get_fernet() -> Fernet:
    from django.conf import settings

    raw = settings.SECRET_KEY.encode("utf-8")
    derived = hashlib.pbkdf2_hmac(
        "sha256", raw, b"mobcash_salt_v1", iterations=100_000, dklen=32
    )
    return Fernet(base64.urlsafe_b64encode(derived))


def _looks_encrypted(value: str) -> bool:
    return bool(value) and value.startswith("gAAAAA")


def encrypt(value: str | None) -> str | None:
    """Chiffre une chaîne pour stockage DB. Idempotent (ne re-chiffre pas)."""
    if not value:
        return value
    # Déjà chiffré avec notre clé → ne pas double-chiffrer
    if _looks_encrypted(value):
        try:
            _get_fernet().decrypt(value.encode("utf-8"))
            return value
        except (InvalidToken, Exception):
            pass
    return _get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt(value: str | None) -> str | None:
    """
    Déchiffre une chaîne avant usage / envoi API.
    Supporte 1 ou 2 couches (rétrocompat double chiffrement accidentel).
    Si la valeur est en clair, la retourne telle quelle.
    """
    if not value:
        return value

    current = value
    for _ in range(3):
        if not _looks_encrypted(current):
            return current
        try:
            current = _get_fernet().decrypt(current.encode("utf-8")).decode("utf-8")
        except (InvalidToken, Exception):
            # Pas chiffré avec notre clé (ancien clair, ou clé différente)
            return current
    return current
