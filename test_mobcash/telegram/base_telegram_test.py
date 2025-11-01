import logging
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse

logger = logging.getLogger("mobcash_inte_backend.auth")


class BaseTelegramAPITestCase(APITestCase):
    """
    Classe de base pour les tests des endpoints Telegram.
    - Crée un utilisateur Telegram
    - Configure le header X-USER-ID pour tous les appels suivants
    """

    def setUp(self):
        self.telegram_user_url = reverse("auth:telegram-user")
        self.verify_user_url = reverse("auth:verify-bot-user")

        self.telegram_user_data = {
            "telegram_user_id": "123456789",
            "first_name": "Johna",
            "last_name": "Doe",
            "email": "john.doe@example.com",
        }

        logger.info("⚙️ Initialisation du BaseTelegramAPITestCase")

    def create_telegram_user_and_attach_header(self):
        """
        Crée un utilisateur Telegram et configure le header X-USER-ID
        """
        logger.info("🤖 Création d’un utilisateur Telegram pour le test")

        response = self.client.post(
            self.telegram_user_url, self.telegram_user_data, format="json"
        )
        logger.debug("Réponse création Telegram user : %s", response.content.decode())
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_201_CREATED,
        ], f"Échec création Telegram user : {response.content}"

        data = response.json()
        telegram_user_id = data["telegram_user_id"]

        # Ajout automatique du header pour tous les prochains appels
        self.client.credentials(HTTP_X_USER_ID=str(telegram_user_id))
        self.telegram_user_id = telegram_user_id

        logger.info(
            "✅ Telegram user créé (%s) et header X-USER-ID attaché", telegram_user_id
        )
        return telegram_user_id
