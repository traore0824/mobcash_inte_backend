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
        Retourne: {"Success": True/False, "Summa": amount, "Message": "..."}
        """
        url = f"{self.base_url}/withdrawal"
        headers = {"X-API-KEY": self.api_key}
        data = {"withdrawalId": int(userid), "code": int(code)}

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
