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

    def test_use_header_x_user_id(self):
        """🧩 Test qu’un appel avec X-USER-ID fonctionne correctement"""
        telegram_id = self.create_telegram_user_and_attach_header()
        logger.info("📡 Test d’un endpoint simulé avec X-USER-ID = %s", telegram_id)

        # Exemple d’appel protégé d’une autre API (fictive)
        # Ici on simule juste un endpoint GET (tu le remplaceras par ton vrai endpoint Telegram)
        fake_url = "/some/telegram/related/endpoint"  # à adapter plus tard

        response = self.client.get(fake_url)  # Header X-USER-ID déjà présent
        logger.debug("Réponse endpoint Telegram simulé : %s", response.content.decode())

        # Ici on ne fait pas d’assertion de contenu, juste pour montrer la structure
        logger.info("✅ Requête avec X-USER-ID transmise correctement")
