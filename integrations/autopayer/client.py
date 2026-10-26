"""Client HTTP AutoPayer — auth ApiKey, timeouts, pas de secret en logs."""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger("mobcash_inte_backend.transactions")

DEFAULT_TIMEOUT = 45


class AutoPayerConfigError(Exception):
    pass


class AutoPayerAPIError(Exception):
    def __init__(self, message: str, status_code: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


def _cfg(name: str) -> str:
    """Lit settings Django puis env (pas de secret loggé)."""
    try:
        from django.conf import settings as dj_settings

        val = getattr(dj_settings, name, None)
        if val:
            return str(val).strip()
    except Exception:
        pass
    return (os.getenv(name) or "").strip()


def _base_url() -> str:
    url = _cfg("AUTOPAYER_BASE_URL").rstrip("/")
    if not url:
        raise AutoPayerConfigError("AUTOPAYER_BASE_URL non configuré")
    return url


def _api_credentials() -> tuple[str, str]:
    key = _cfg("AUTOPAYER_API_KEY")
    secret = _cfg("AUTOPAYER_API_SECRET")
    if not key or not secret:
        raise AutoPayerConfigError("AUTOPAYER_API_KEY / AUTOPAYER_API_SECRET non configurés")
    return key, secret


def _auth_header() -> str:
    key, secret = _api_credentials()
    return f"ApiKey {key}:{secret}"


def _headers() -> dict[str, str]:
    return {
        "Authorization": _auth_header(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def request(
    method: str,
    path: str,
    *,
    json_body: dict | None = None,
    params: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """
    Appel AutoPayer. Ne log jamais api_secret ni Authorization.
    """
    url = f"{_base_url()}{path}"
    safe_body = None
    if json_body is not None:
        safe_body = {k: v for k, v in json_body.items() if k not in {"api_secret", "secret"}}

    logger.info(
        "[AUTOPAYER] %s %s body=%s params=%s",
        method.upper(),
        path,
        safe_body,
        params,
    )

    try:
        resp = requests.request(
            method=method.upper(),
            url=url,
            headers=_headers(),
            json=json_body,
            params=params,
            timeout=timeout,
        )
    except requests.Timeout as exc:
        raise AutoPayerAPIError(f"Timeout AutoPayer: {exc}") from exc
    except requests.RequestException as exc:
        raise AutoPayerAPIError(f"Erreur réseau AutoPayer: {exc}") from exc

    try:
        payload = resp.json() if resp.content else {}
    except ValueError:
        payload = {"raw": (resp.text or "")[:500]}

    if resp.status_code >= 400:
        logger.error(
            "[AUTOPAYER] HTTP %s path=%s payload=%s",
            resp.status_code,
            path,
            payload,
        )
        raise AutoPayerAPIError(
            f"AutoPayer HTTP {resp.status_code}",
            status_code=resp.status_code,
            payload=payload,
        )

    if isinstance(payload, dict) and payload.get("success") is False:
        raise AutoPayerAPIError(
            payload.get("message") or "AutoPayer success=false",
            status_code=resp.status_code,
            payload=payload,
        )

    return payload if isinstance(payload, dict) else {"data": payload}
