import logging
from rest_framework import status
from .base_telegram_test import BaseTelegramAPITestCase

logger = logging.getLogger("mobcash_inte_backend.auth")


class TelegramUserTests(BaseTelegramAPITestCase):
    """Tests complets pour les utilisateurs Telegram"""

    def test_create_telegram_user(self):
        """✅ Test création d’un utilisateur Telegram"""
        logger.info("🚀 Test création Telegram user")

        response = self.client.post(
            self.telegram_user_url, self.telegram_user_data, format="json"
        )
        logger.debug("Réponse création Telegram : %s", response.content.decode())

        self.assertIn(
            response.status_code, [status.HTTP_200_OK, status.HTTP_201_CREATED]
        )
        data = response.json()

        self.assertEqual(
            data["telegram_user_id"], self.telegram_user_data["telegram_user_id"]
        )
        self.assertEqual(data["email"], self.telegram_user_data["email"])
        logger.info("✅ Telegram user créé avec succès : %s", data["telegram_user_id"])

    def test_verify_bot_user_not_exist(self):
        """🔍 Test de vérification d’un utilisateur Telegram qui n’existe pas"""
        logger.info("🔎 Vérification d’un utilisateur Telegram inexistant")

        params = {"telegram_user_id": "999999999"}  # ID inexistant
        response = self.client.get(self.verify_user_url, params)
        logger.debug("Réponse vérification inexistant : %s", response.content.decode())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertIn("user_exist", data)
        self.assertFalse(data["user_exist"])
        logger.info("✅ Vérification OK : utilisateur inexistant détecté")

    def test_verify_bot_user_exist(self):
        """✅ Test vérification d’un utilisateur Telegram qui existe"""
        logger.info("🔎 Création d’un utilisateur Telegram avant vérification")

        # Crée l’utilisateur Telegram
        self.client.post(self.telegram_user_url, self.telegram_user_data, format="json")

        params = {"telegram_user_id": self.telegram_user_data["telegram_user_id"]}
        response = self.client.get(self.verify_user_url, params)
        logger.debug("Réponse vérification existant : %s", response.content.decode())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertIn("user_exist", data)
        self.assertTrue(data["user_exist"])
        logger.info("✅ Vérification OK : utilisateur Telegram existant confirmé")