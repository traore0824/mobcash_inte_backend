import requests
import logging

logger = logging.getLogger("mobcash_inte_backend.transactions")


class OneWinService:

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.1win.win/v1/client"

    def recharge_account(self, userid, amount: float):
        """
        Dépôt 1win — normalisé pour être compatible avec le reste du code.
        Retourne: {"Success": True/False, "Summa": amount, "Message": "..."}
        """
        url = f"{self.base_url}/deposit"
        headers = {"X-API-KEY": self.api_key}
        data = {"userId": int(userid), "amount": amount}

        try:
            response = requests.post(url, json=data, headers=headers, timeout=30)
            logger.info(f"[1WIN] [DEPOSIT] status={response.status_code} body={response.text[:300]}")

            if response.status_code in (200, 201):
                raw = response.json()
                return {
                    "Success": True,
                    "Summa": raw.get("amount"),
                    "Message": "Dépôt effectué avec succès",
                    "raw": raw,
                }
            else:
                return {
                    "Success": False,
                    "Message": f"Erreur {response.status_code}: {response.text[:200]}",
                }

        except Exception as e:
            logger.error(f"[1WIN] [DEPOSIT] Exception: {e}")
            return {"Success": False, "Message": str(e)}

    def withdraw_from_account(self, userid, code):
        """
        Retrait 1win — normalisé pour être compatible avec le reste du code.
        Pour 1win : withdrawalId = withdriwal_code (ID retrait transmis par le joueur)
                    code = code secret du joueur
        Retourne: {"Success": True/False, "Summa": amount, "Message": "..."}
        """
        url = f"{self.base_url}/withdrawal"
        headers = {"X-API-KEY": self.api_key}
        # Pour 1win, 'userid' reçu ici est en réalité le withdriwal_code (ID du retrait)
        # et 'code' est le code secret transmis par le joueur
        data = {"withdrawalId": str(code), "code": str(userid)}

        try:
            response = requests.post(url, json=data, headers=headers, timeout=30)
            logger.info(f"[1WIN] [WITHDRAWAL] status={response.status_code} body={response.text[:300]}")

            if response.status_code in (200, 201):
                raw = response.json()
                return {
                    "Success": True,
                    "Summa": raw.get("amount"),
                    "Message": "Retrait effectué avec succès",
                    "raw": raw,
                }
            else:
                return {
                    "Success": False,
                    "Message": f"Erreur {response.status_code}: {response.text[:200]}",
                }

        except Exception as e:
            logger.error(f"[1WIN] [WITHDRAWAL] Exception: {e}")
            return {"Success": False, "Message": str(e)}


plateform = OneWinService(
    api_key="ebfad3fbccb250211271dd519da8b9e9c10d4797a9ea6f772ee34245c4e6ee0f"
)
# plateform.withdraw_from_account(userid="339966934", code="768429")
print(f"Test de retrait: {plateform.withdraw_from_account(userid='339966934', code='768429')}")
