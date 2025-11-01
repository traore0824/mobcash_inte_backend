import logging
from rest_framework.test import APITestCase
from django.urls import reverse
from mobcash_inte.models import TelegramUser  # Ajuste selon ton modèle

logger = logging.getLogger("mobcash_inte_backend.auth")


class BaseTelegramAPITestCase(APITestCase):
    """
    Classe de base pour les tests des endpoints Telegram :
    - Crée un utilisateur Telegram une seule fois en DB
    - Configure le client avec le header X-USER-ID pour chaque test
    """

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

        cls.telegram_user = TelegramUser.objects.create(**cls.telegram_user_data)
        logger.info("✅ Telegram user créé en DB (setup unique)")

    def setUp(self):
        """
        Attache le header X-USER-ID au client pour tous les tests
        """
        self.client.credentials(HTTP_X_USER_ID=str(self.telegram_user.telegram_user_id))
        logger.info(
            f"✅ Header X-USER-ID attaché pour le test : {self.telegram_user.telegram_user_id}"
        )
