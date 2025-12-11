import requests
from datetime import datetime
import constant
import base64, hashlib


class BetApp:
    def __init__(self, hash=None, cashier_pass=None, cashdesk_id=None):
        self.hash = hash
        self.cashier_pass = cashier_pass
        self.cashdesk_id = cashdesk_id

    def current_time(self):
        date = datetime.utcnow()
        return date.strptime("%d-%b-%Y-%H:%M:%S")

    def generate_signatures(self, userid: str, amount: float):
        sha256_initial = hashlib.sha256(
            f"hash={self.hash}&lng=fr&userid={userid}".encode()
        ).hexdigest()

        md5_params = hashlib.md5(
            f"summa={amount}&cashierpass={self.cashier_pass}&cashdeskid={self.cashdesk_id}".encode()
        ).hexdigest()

        final_signature = hashlib.sha256(
            f"{sha256_initial}{md5_params}".encode()
        ).hexdigest()
        confirm = hashlib.md5(f"{userid}:{self.hash}".encode()).hexdigest()

        return {"signature": final_signature, "confirm": confirm}

    def generate_payout_signatures(self, userid: str, code: str):
        sha256_initial = hashlib.sha256(
            f"hash={self.hash}&lng=fr&userid={userid}".encode()
        ).hexdigest()

        md5_params = hashlib.md5(
            f"code={code}&cashierpass={self.cashier_pass}&cashdeskid={self.cashdesk_id}".encode()
        ).hexdigest()

        final_signature = hashlib.sha256(
            f"{sha256_initial}{md5_params}".encode()
        ).hexdigest()
        confirm = hashlib.md5(f"{userid}:{self.hash}".encode()).hexdigest()

        return {"signature": final_signature, "confirm": confirm}

    def generate_balance_signatures(self, date: str):
        sha256_initial = hashlib.sha256(
            f"hash={self.hash}&cashdeskid={self.cashdesk_id}&dt={date}".encode()
        ).hexdigest()

        md5_params = hashlib.md5(
            f"dt={date}&cashierpass={self.cashier_pass}&cashdeskid={self.cashdesk_id}".encode()
        ).hexdigest()

        final_signature = hashlib.sha256(
            f"{sha256_initial}{md5_params}".encode()
        ).hexdigest()
        confirm = hashlib.md5(f"{self.cashdesk_id}:{self.hash}".encode()).hexdigest()

        return {"signature": final_signature, "confirm": confirm}

    def recharge_account(self, userid: str, amount: float):
        try:
            signatures = self.generate_signatures(userid, amount)

            url = f"https://partners.servcul.com/CashdeskBotAPI/Deposit/{userid}/Add"
            headers = {
                "Content-Type": "application/json",
                "Sign": signatures["signature"],
            }
            data = {
                "cashdeskid": int(self.cashdesk_id),
                "lng": "fr",
                "summa": float(amount),
                "confirm": signatures["confirm"],
            }

            response = requests.post(url=url, json=data, headers=headers)
            print(f"status {response.status_code}")
            return {
                "code": constant.CODE_SUCCESS,
                "data": response.json(),
                "status": response.status_code,
            }

        except Exception as e:
            return {"code": constant.CODE_EXEPTION, "error": str(e)}

    def withdraw_from_account(self, userid: str, code: str):
        try:
            signatures = self.generate_payout_signatures(userid, code)

            url = f"https://partners.servcul.com/CashdeskBotAPI/Deposit/{userid}/Payout"
            headers = {
                "Content-Type": "application/json",
                "Sign": signatures["signature"],
            }
            data = {
                "cashdeskId": int(self.cashdesk_id),
                "lng": "fr",
                "code": code,
                "confirm": signatures["confirm"],
            }

            response = requests.post(url=url, json=data, headers=headers)
            return {"code": constant.CODE_SUCCESS, "data": response.json()}

        except requests.exceptions.RequestException as e:
            error_detail = {
                "message": str(e),
                "response": getattr(e.response, "text", None),
                "status": getattr(e.response, "status_code", None),
            }
            raise {"code": constant.CODE_EXEPTION}

    def check_balance(self):
        try:
            date = self.current_time()
            print(date)
            signatures = self.generate_balance_signatures(date)
            # Construction de l'URL de base sans paramètres
            base_url = f"https://partners.servcul.com/CashdeskBotAPI/Cashdesk/{self.cashdesk_id}/Balance"

            headers = {
                "Content-Type": "application/json",
                "Sign": signatures["signature"],
            }

            # Utiliser requests.get avec params pour gérer correctement l'encodage
            response = requests.get(
                url=base_url,
                params={"confirm": signatures["confirm"], "dt": date},
                headers=headers,
            )

            print(f"Final URL: {response.url}")  # Pour debug
            print(f"Headers: {headers}")  # Pour debug

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            error_detail = {
                "message": str(e),
                "response": getattr(e.response, "text", None),
                "status": getattr(e.response, "status_code", None),
            }
            return {"code": constant.CODE_EXEPTION, "error": error_detail}

    def generate_user_search_signatures(self, userid: str):
        sha256_initial = hashlib.sha256(
            f"hash={self.hash}&userid={userid}&cashdeskid={self.cashdesk_id}".encode()
        ).hexdigest()

        md5_params = hashlib.md5(
            f"userid={userid}&cashierpass={self.cashier_pass}&hash={self.hash}".encode()
        ).hexdigest()

        final_signature = hashlib.sha256(
            f"{sha256_initial}{md5_params}".encode()
        ).hexdigest()

        confirm = hashlib.md5(f"{userid}:{self.hash}".encode()).hexdigest()

        return {"signature": final_signature, "confirm": confirm}

    def search_user(self, userid: str):
        """Recherche un utilisateur par son ID"""
        try:
            signatures = self.generate_user_search_signatures(userid)

            base_url = f"https://partners.servcul.com/CashdeskBotAPI/Users/{userid}"

            headers = {
                "Content-Type": "application/json",
                "Sign": signatures["signature"],
            }

            # Paramètres de la requête GET
            params = {"confirm": signatures["confirm"], "cashdeskid": self.cashdesk_id}

            response = requests.get(url=base_url, params=params, headers=headers)

            print(f"Final URL: {response.url}")  # Pour debug
            print(f"Status: {response.status_code}")  # Pour debug

            response.raise_for_status()
            return {
                "code": constant.CODE_SUCCESS,
                "data": response.json(),
                "status": response.status_code,
            }

        except requests.exceptions.RequestException as e:
            error_detail = {
                "message": str(e),
                "response": getattr(e.response, "text", None),
                "status": getattr(e.response, "status_code", None),
            }
            return {"code": constant.CODE_EXEPTION, "error": error_detail}


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

