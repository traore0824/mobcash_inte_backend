"""
Client HTTP BeWallet — External API (topup/payout/status) + Dealer API legacy (solde/stats).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger("mobcash_inte")

_DEFAULT_BASE = "https://api.merchant.be-wallet.app/api/v1"


class BetmomoAPIError(Exception):
    """Erreur retournée par l'API BeWallet."""


class BetmomoAuthError(BetmomoAPIError):
    """Authentification BetMomo invalide ou expirée."""


def _base_url(attr: str) -> str:
    return str(getattr(settings, attr, None) or _DEFAULT_BASE).rstrip("/")


class BetmomoClient:
    """
    External API : token app dealer (dat_...) — topup, payout, status.
    Dealer API (legacy) : email/password → login → GET /dealer/stats pour le solde.
    """

    def __init__(
        self,
        token: str,
        *,
        email: str | None = None,
        password: str | None = None,
        external_base_url: str | None = None,
        dealer_base_url: str | None = None,
        timeout: int = 30,
    ):
        if not token:
            raise ValueError("Token BetMomo (dat_...) manquant")
        self.external_token = token.strip()
        self.email = email.strip() if email else None
        self.password = password
        self.timeout = timeout
        self.dealer_token: str | None = None

        self.external_base_url = (
            external_base_url or _base_url("BEWALLET_EXTERNAL_API_BASE_URL")
        ).rstrip("/")
        self.dealer_base_url = (
            dealer_base_url or _base_url("BEWALLET_DEALER_API_BASE_URL")
        ).rstrip("/")

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    def _parse_error(self, response: requests.Response) -> str:
        try:
            body = response.json()
            error = body.get("error")
            if isinstance(error, dict):
                return error.get("message") or error.get("code") or str(error)
            return body.get("message") or str(body)
        except ValueError:
            return response.text or f"HTTP {response.status_code}"

    def _request_external(
        self,
        method: str,
        path: str,
        *,
        payload: dict | None = None,
    ) -> dict[str, Any]:
        url = f"{self.external_base_url}{path}"
        headers = {"Authorization": f"Bearer {self.external_token}"}
        response = self.session.request(
            method,
            url,
            json=payload,
            headers=headers,
            timeout=self.timeout,
        )

        if response.status_code == 401:
            raise BetmomoAuthError(self._parse_error(response))
        if response.status_code >= 400:
            raise BetmomoAPIError(self._parse_error(response))
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    @staticmethod
    def login(
        email: str,
        password: str,
        *,
        base_url: str | None = None,
        timeout: int = 30,
    ) -> str:
        """POST /auth/login — obtient un Bearer token (ancienne API dealer)."""
        dealer_url = (base_url or _base_url("BEWALLET_DEALER_API_BASE_URL")).rstrip("/")

        response = requests.post(
            f"{dealer_url}/auth/login",
            json={"email": email, "password": password},
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "x-client-type": "dealer",
                "x-requested-with": "XMLHttpRequest",
            },
            timeout=timeout,
        )
        if response.status_code != 200:
            raise BetmomoAuthError(BetmomoClient._parse_error_static(response))

        payload = response.json()
        token = payload.get("token")
        if not token:
            raise BetmomoAuthError("Réponse login BetMomo sans token")
        return str(token)

    @staticmethod
    def _parse_error_static(response: requests.Response) -> str:
        try:
            body = response.json()
            return body.get("message") or str(body)
        except ValueError:
            return response.text or f"HTTP {response.status_code}"

    def _ensure_dealer_token(self) -> str:
        if self.dealer_token:
            return self.dealer_token
        if not self.email or not self.password:
            raise BetmomoAuthError(
                "Email/mot de passe dealer requis pour consulter le solde (POST /auth/login)"
            )
        self.dealer_token = self.login(
            self.email,
            self.password,
            base_url=self.dealer_base_url,
            timeout=self.timeout,
        )
        return self.dealer_token

    def _refresh_dealer_token(self) -> str:
        if not self.email or not self.password:
            raise BetmomoAuthError("Token dealer expiré — identifiants requis")
        logger.warning("Token dealer BetMomo expiré (401) — login puis retry")
        self.dealer_token = self.login(
            self.email,
            self.password,
            base_url=self.dealer_base_url,
            timeout=self.timeout,
        )
        return self.dealer_token

    def _request_dealer(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        retry_on_unauthorized: bool = True,
    ) -> dict[str, Any]:
        token = self._ensure_dealer_token()
        url = f"{self.dealer_base_url}{path}"
        headers = {"Authorization": f"Bearer {token}"}

        response = self.session.request(
            method,
            url,
            params=params,
            headers=headers,
            timeout=self.timeout,
        )

        if response.status_code == 401 and retry_on_unauthorized:
            token = self._refresh_dealer_token()
            headers = {"Authorization": f"Bearer {token}"}
            response = self.session.request(
                method,
                url,
                params=params,
                headers=headers,
                timeout=self.timeout,
            )

        if response.status_code == 401:
            raise BetmomoAuthError(self._parse_error(response))
        if response.status_code >= 400:
            raise BetmomoAPIError(self._parse_error(response))
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    def stats(self, interval: str = "day", start_date: str | None = None) -> dict[str, Any]:
        """GET /dealer/stats — solde dealer (ancienne API)."""
        if start_date is None:
            start_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00.000Z")
        return self._request_dealer(
            "GET",
            "/dealer/stats",
            params={"interval": interval, "start_date": start_date},
        )

    def topup(self, player_id: str, amount: float) -> dict[str, Any]:
        return self._request_external(
            "POST",
            "/dealer/external/topup",
            payload={"player_id": str(player_id), "amount": float(amount)},
        )

    def payout(self, player_id: str, pin: str) -> dict[str, Any]:
        return self._request_external(
            "POST",
            "/dealer/external/payout",
            payload={"player_id": str(player_id), "pin": str(pin)},
        )

    def topup_status(self, reference: str) -> dict[str, Any]:
        return self._request_external(
            "GET",
            f"/dealer/external/topup/{reference}/status",
        )

    def payout_status(self, transaction_id: str) -> dict[str, Any]:
        return self._request_external(
            "GET",
            f"/dealer/external/payout/{transaction_id}/status",
        )
