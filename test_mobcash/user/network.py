from django.urls import reverse
from rest_framework import status

from test_mobcash.user.base_test import BaseAPITestCase



class NetworkAPITestUserToken(BaseAPITestCase):
    """
    Test l'API /mobcash/network pour un user classique avec Bearer Token
    """

    app_name = "mobcash_inte"

    def setUp(self):
        super().setUp()
        self.url = reverse("mobcash_inte:network")  # on utilise app_name
        # BaseAPITestCase gère déjà le token dans self.client

    def test_network_list_user_token(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.json(), list)
        if response.json():
            self.assertIn("id", response.json()[0])
            self.assertIn("name", response.json()[0])
