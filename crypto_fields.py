"""
crypto_fields.py
================
Utilitaires de chiffrement symétrique (Fernet) pour les champs sensibles en DB.

La clé Fernet est dérivée du SECRET_KEY Django via PBKDF2 + SHA256.
On n'utilise PAS directement SECRET_KEY car Fernet exige une clé de 32 octets
encodée en base64url — la dérivation garantit ce format quelle que soit la valeur
de SECRET_KEY.

Usage dans les models :
    from crypto_fields import encrypt, decrypt

    class MyModel(models.Model):
        _hash_encrypted = models.TextField(blank=True, null=True, db_column='hash')

        @property
        def hash(self):
            return decrypt(self._hash_encrypted)

        @hash.setter
        def hash(self, value):
            self._hash_encrypted = encrypt(value)
"""

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken


def _get_fernet() -> Fernet:
    """
    Dérive une clé Fernet 32 octets depuis le SECRET_KEY Django.
    Importé ici (pas au module level) pour éviter les problèmes d'init Django.
    """
    from django.conf import settings

    raw = settings.SECRET_KEY.encode("utf-8")
    # PBKDF2-SHA256 → 32 octets → base64url → clé Fernet valide
    derived = hashlib.pbkdf2_hmac("sha256", raw, b"mobcash_salt_v1", iterations=100_000, dklen=32)
    key = base64.urlsafe_b64encode(derived)
    return Fernet(key)


def encrypt(value: str | None) -> str | None:
    """Chiffre une chaîne. Retourne None si value est None ou vide."""
    if not value:
        return value
    f = _get_fernet()
    return f.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt(value: str | None) -> str | None:
    """
    Déchiffre une chaîne. Retourne None si value est None ou vide.
    Si la valeur n'est pas chiffrée (données existantes en clair),
    la retourne telle quelle pour assurer la rétrocompatibilité.
    """
    if not value:
        return value
    try:
        f = _get_fernet()
        return f.decrypt(value.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception):
        # Valeur en clair (données existantes avant migration) — retour direct
        return value
