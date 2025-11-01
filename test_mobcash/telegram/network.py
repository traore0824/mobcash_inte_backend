from django.urls import reverse
from rest_framework import status
from .base import BaseTelegramAPITestCase  # ton BaseTelegramAPITestCase


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
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.json(), list)
        if response.json():
            self.assertIn("id", response.json()[0])
            self.assertIn("name", response.json()[0])
