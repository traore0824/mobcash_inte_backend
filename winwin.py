"""
Service Python pour l'intégration de l'API Cash Agent
"""

import requests


class CashAPIService:

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.1win.win/v1/client"

    def create_deposit(self, user_id: int, amount: float):
        """Créer un dépôt"""
        url = f"{self.base_url}/deposit"
        headers = {"X-API-KEY": self.api_key}
        data = {"userId": user_id, "amount": amount}

        response = requests.post(url, json=data, headers=headers, timeout=30)
        return response.json()

    def process_withdrawal(self, withdrawal_id: int, code: int):
        """Traiter un retrait"""
        url = f"{self.base_url}/withdrawal"
        headers = {"X-API-KEY": self.api_key}
        data = {"withdrawalId": withdrawal_id, "code": code}

        response = requests.post(url, json=data, headers=headers, timeout=30)
        return response.json()


# Utilisation
if __name__ == "__main__":
    api = CashAPIService(
        api_key="ebfad3fbccb250211271dd519da8b9e9c10d4797a9ea6f772ee34245c4e6ee0f"
    )

    # Dépôt
    result = api.create_deposit(user_id=298, amount=200)
    print(result)

    # Retrait
    result = api.process_withdrawal(withdrawal_id=123, code=456789)
    print(result)
