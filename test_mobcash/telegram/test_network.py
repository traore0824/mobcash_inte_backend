import logging
from django.urls import reverse
from rest_framework import status
from test_mobcash.telegram.base_telegram_test import BaseTelegramAPITestCase

logger = logging.getLogger("mobcash_inte_backend.network")


class NetworkAPITestTelegramUser(BaseTelegramAPITestCase):
    """
    Test l'API /mobcash/network pour un user Telegram avec X-USER-ID
    """

    app_name = "mobcash_inte"

    def setUp(self):
        super().setUp()
        self.url = reverse("mobcash_inte:network")  # on utilise app_name
        # BaseTelegramAPITestCase gère déjà l'en-tête X-USER-ID dans self.client

    def test_network_list_telegram_user(self):
        # Crée un Telegram user et attache automatiquement le header
        telegram_user_id = self.create_telegram_user_and_attach_header()

        response = self.client.get(self.url)
        content = response.content.decode()
        logger.info("Réponse /network pour Telegram user : %s", content)

        self.assertEqual(
            response.status_code, status.HTTP_200_OK, f"Échec status : {content}"
        )

        data = response.json()
        if not data:
            self.fail(f"La liste est vide ! Contenu complet : {content}")

        self.assertIsInstance(data, list)
        self.assertIn("id", data[0])
        self.assertIn("name", data[0])
        logger.info(
            "✅ /network pour Telegram user renvoie au moins un élément avec 'id' et 'name'"
        )


