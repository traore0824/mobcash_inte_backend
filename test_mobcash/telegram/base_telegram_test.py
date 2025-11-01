import logging
from rest_framework.test import APITestCase
from django.urls import reverse
from rest_framework import status

logger = logging.getLogger("mobcash_inte_backend.auth")


class BaseTelegramAPITestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.telegram_user_url = reverse("auth:telegram-user")
        cls.verify_user_url = reverse("auth:verify-bot-user")

        cls.telegram_user_data = {
            "telegram_user_id": "123456789",
            "first_name": "Johna",
            "last_name": "Doe",
            "email": "john.doe@example.com",
        }

        logger.info("⚙️ Initialisation du BaseTelegramAPITestCase (une seule fois)")

        cls._create_telegram_user_and_attach_header()  # ✅ plus d'argument ici

    @classmethod
    def _create_telegram_user_and_attach_header(cls):
        logger.info("🤖 Création d’un utilisateur Telegram (setup unique)")

        response = cls().client.post(
            cls.telegram_user_url, cls.telegram_user_data, format="json"
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_201_CREATED,
        ], f"Échec création Telegram user : {response.content}"

        data = response.json()
        telegram_user_id = data["telegram_user_id"]

        cls.client.credentials(HTTP_X_USER_ID=str(telegram_user_id))
        cls.telegram_user_id = telegram_user_id

        logger.info(
            "✅ Telegram user créé (%s) et header X-USER-ID attaché", telegram_user_id
        )
