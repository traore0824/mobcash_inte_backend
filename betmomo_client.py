"""
Client Python de référence pour l'API Betmomo Agent (be-wallet).

Base API : https://api.merchant.be-wallet.app/api/v1
Auth     : token Bearer (récupéré depuis localStorage['agent-auth-user'].token
           APRÈS connexion via l'interface).

Couverture :
  - LECTURE : stats, operations, players, numbers, countries, operators (testée).
  - ÉCRITURE : create_transaction() -> POST /dealer/transactions (recharge topup /
    retrait payout). Le corps exact des champs est À CONFIRMER par capture réseau
    réelle ; les helpers topup()/payout() sont fournis mais DÉSACTIVÉS par défaut
    (dry_run=True) pour éviter tout transfert involontaire.

Destiné à servir de base d'intégration pour le développeur de la plateforme cible.

Usage :
    export BETMOMO_TOKEN="<token>"
    python betmomo_client.py
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import requests


class BetmomoClient:
    BASE_URL = "https://api.merchant.be-wallet.app/api/v1"

    def __init__(self, token: str, active_profile: str = "field", timeout: int = 30):
        if not token:
            raise ValueError("Token manquant (localStorage['agent-auth-user'].token).")
        self.token = token
        self.active_profile = active_profile
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

    # ------------------------------------------------------------------ #
    # AUTHENTIFICATION — POST /auth/login (CONFIRMÉ)
    # ------------------------------------------------------------------ #
    @classmethod
    def login(cls, email: str, password: str, recaptcha: str, timeout: int = 30) -> dict:
        """
        Connexion de l'agent. Corps CONFIRMÉ : { email, password, recaptcha }.
        Le champ `recaptcha` est un token Google reCAPTCHA INVISIBLE (v3) : aucun défi
        visible au login, mais le frontend génère un token en arrière-plan et l'API
        l'exige. Une auth automatisée (hors navigateur) doit donc pouvoir en produire un.
        Renvoie la réponse JSON (contient le token Bearer).

        Exemple :
            data = BetmomoClient.login(email, password, recaptcha_token)
            client = BetmomoClient(token=data["token"])  # nom exact du champ à vérifier
        """
        r = requests.post(
            f"{cls.BASE_URL}/auth/login",
            json={"email": email, "password": password, "recaptcha": recaptcha},
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=timeout,
        )
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------ #
    # Helpers HTTP
    # ------------------------------------------------------------------ #
    def _get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        r = self.session.get(f"{self.BASE_URL}{path}", params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, payload: dict) -> dict[str, Any]:
        r = self.session.post(f"{self.BASE_URL}{path}", json=payload, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------ #
    # LECTURE
    # ------------------------------------------------------------------ #
    def stats(self, interval: str = "day", start_date: str | None = None) -> dict:
        if start_date is None:
            start_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00.000Z")
        return self._get("/dealer/stats", {"interval": interval, "start_date": start_date})

    def operations(self, page: int = 1, per_page: int = 20,
                   include: str = "dealerMovements,topUp,payOut",
                   sort: str = "-timestamp") -> dict:
        return self._get("/dealer/operations", {
            "per_page": per_page, "paginate": per_page, "page": page,
            "include": include, "sort": sort, "active_profile": self.active_profile,
        })

    def players(self, page: int = 1, per_page: int = 20) -> dict:
        return self._get("/dealer/players", {"per_page": per_page, "paginate": per_page, "page": page})

    def numbers(self) -> dict:
        return self._get("/dealer/numbers")

    def countries(self, active_only: bool = True) -> dict:
        return self._get("/countries", {"filter[is_active]": "true"} if active_only else None)

    def operators(self, country_id: int) -> dict:
        return self._get("/operators", {"filter[country_id]": country_id})

    def iter_operations(self, per_page: int = 50, **kw):
        page = 1
        while True:
            res = self.operations(page=page, per_page=per_page, **kw)
            data = res.get("data", [])
            if not data:
                break
            yield from data
            meta = res.get("meta") or {}
            if not meta or page >= meta.get("last_page", page):
                break
            page += 1

    # ------------------------------------------------------------------ #
    # ÉCRITURE
    #   POST /dealer/transactions/topup   (recharge) — CONFIRMÉ
    #   POST /dealer/transactions/payout  (retrait)  — à confirmer
    # ------------------------------------------------------------------ #
    # ⚠️ Ces opérations déplacent de l'argent réel. À n'exécuter que par un
    #    appel serveur maîtrisé, jamais automatiquement. dry_run=True par défaut.

    def topup(self, player_id: str, amount: float, dry_run: bool = True) -> dict:
        """
        Recharge d'un joueur. Corps CONFIRMÉ : { player_id, amount }.
        POST /dealer/transactions/topup
        """
        payload = {"player_id": player_id, "amount": amount}
        if dry_run:
            return {"dry_run": True, "would_POST": "/dealer/transactions/topup", "payload": payload}
        return self._post("/dealer/transactions/topup", payload)

    def payout(self, player_id: str, pin: str, dry_run: bool = True) -> dict:
        """
        Retrait d'un joueur. Corps CONFIRMÉ : { player_id, pin }.
        Le champ du code de retrait s'appelle `pin`. Il N'Y A PAS de champ `amount` :
        le montant est déterminé côté serveur à partir du pin (le code encode le montant).
        POST /dealer/transactions/payout
        """
        payload = {"player_id": player_id, "pin": pin}
        if dry_run:
            return {"dry_run": True, "would_POST": "/dealer/transactions/payout",
                    "payload": {"player_id": player_id, "pin": "<masqué>"}}
        return self._post("/dealer/transactions/payout", payload)


if __name__ == "__main__":
    token = os.environ.get("BETMOMO_TOKEN")
    if not token:
        raise SystemExit("Définis BETMOMO_TOKEN avant de lancer ce script.")
    c = BetmomoClient(token=token)

    print("== Stats ==")
    print(c.stats())

    print("\n== 5 dernières opérations ==")
    for op in c.operations(per_page=5).get("data", []):
        print(f"  {op.get('ref'):<28} {op.get('type'):<10} {op.get('amount')} {op.get('currency')}  {op.get('status')}")

    print("\n== Exemple d'écriture (dry-run, aucun transfert) ==")
    print(c.topup(player_id="108464223", amount=1000))          # dry_run par défaut
    print(c.payout(player_id="108464223", pin="******"))
