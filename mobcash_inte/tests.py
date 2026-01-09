from datetime import datetime, timezone
import requests
import hashlib


class BetApp:
    def __init__(self, hash=None, cashier_pass=None, cashdesk_id=None):
        self.hash = hash
        self.cashier_pass = cashier_pass
        self.cashdesk_id = cashdesk_id

    def current_time(self):
        """Retourne la date/heure en UTC+0 au format attendu par l'API"""
        utc_time = datetime.now(timezone.utc)
        formatted_time = utc_time.strftime("%Y.%m.%d %H:%M:%S")
        print(f"⏰ UTC (utilisé): {formatted_time}")
        return formatted_time

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
        print(f"\n🔐 Debug signatures:")
        print(f"   Date (non encodée): '{date}'")

        sha256_string = f"hash={self.hash}&cashdeskid={self.cashdesk_id}&dt={date}"
        sha256_initial = hashlib.sha256(sha256_string.encode()).hexdigest()

        md5_string = (
            f"dt={date}&cashierpass={self.cashier_pass}&cashdeskid={self.cashdesk_id}"
        )
        md5_params = hashlib.md5(md5_string.encode()).hexdigest()

        combined = f"{sha256_initial}{md5_params}"
        final_signature = hashlib.sha256(combined.encode()).hexdigest()

        confirm = hashlib.md5(f"{self.cashdesk_id}:{self.hash}".encode()).hexdigest()

        print(f"   SHA256 string: {sha256_string}")
        print(f"   SHA256 initial: {sha256_initial}")
        print(f"   MD5 string: {md5_string}")
        print(f"   MD5 params: {md5_params}")
        print(f"   Combined: {combined}")
        print(f"   Signature finale: {final_signature}")
        print(f"   Confirm: {confirm}\n")

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
                "code": 200,
                "data": response.json(),
                "status": response.status_code,
            }

        except Exception as e:
            return {"code": 500, "error": str(e)}

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
            return {"code": 200, "data": response.json()}

        except requests.exceptions.RequestException as e:
            error_detail = {
                "message": str(e),
                "response": getattr(e.response, "text", None),
                "status": getattr(e.response, "status_code", None),
            }
            return {"code": 500, "error": error_detail}

    def check_balance(self):
        try:
            date = self.current_time()
            signatures = self.generate_balance_signatures(date)

            base_url = f"https://partners.servcul.com/CashdeskBotAPI/Cashdesk/{self.cashdesk_id}/Balance"
            headers = {
                "Content-Type": "application/json",
                "Sign": signatures["signature"],
            }

            # 🚨 Ne pas utiliser params pour ne pas encoder la date
            url = f"{base_url}?confirm={signatures['confirm']}&dt={date}"

            response = requests.get(url=url, headers=headers)

            print(f"🌐 Final URL: {response.url}")
            print(f"📡 Status: {response.status_code}")

            if response.status_code != 200:
                print(f"❌ Response: {response.text}")

            response.raise_for_status()
            return {"code": 200, "data": response.json()}

        except requests.exceptions.RequestException as e:
            error_detail = {
                "message": str(e),
                "response": getattr(e.response, "text", None),
                "status": getattr(e.response, "status_code", None),
            }
            return {"code": 500, "error": error_detail}

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
        try:
            signatures = self.generate_user_search_signatures(userid)

            base_url = f"https://partners.servcul.com/CashdeskBotAPI/Users/{userid}"
            headers = {
                "Content-Type": "application/json",
                "Sign": signatures["signature"],
            }

            params = {"confirm": signatures["confirm"], "cashdeskid": self.cashdesk_id}

            response = requests.get(url=base_url, params=params, headers=headers)

            print(f"Final URL: {response.url}")
            print(f"Status: {response.status_code}")

            response.raise_for_status()
            return {
                "code": 200,
                "data": response.json(),
                "status": response.status_code,
            }

        except requests.exceptions.RequestException as e:
            error_detail = {
                "message": str(e),
                "response": getattr(e.response, "text", None),
                "status": getattr(e.response, "status_code", None),
            }
            return {"code": 500, "error": error_detail}


# 🎯 Exemple de test
if __name__ == "__main__":
    checker = BetApp(
        hash="23b30d521af3a55640cf4114d5e278349b2972a32b746d325269b2fceeeab2fe",
        cashier_pass="0017oSG^0YF=",
        cashdesk_id="1432926",
    )
    print("=" * 60)
    print("🧪 TEST CHECK_BALANCE")
    print("=" * 60)

    resultat = checker.search_user(userid="1521027305")
    print(f"\n📊 Réponse: {resultat}")

    if resultat.get("code") == 200 and "data" in resultat:
        data = resultat["data"]
        print(f"\n✅ ✅ ✅ SUCCESS! ✅ ✅ ✅")
        print(f"💰 Balance: {data.get('Balance', 'N/A')}")
        print(f"🔒 Limit: {data.get('Limit', 'N/A')}")
    else:
        print(f"\n❌ ERREUR: {resultat.get('error')}")
