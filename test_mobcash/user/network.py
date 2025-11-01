import logging
from django.urls import reverse
from rest_framework import status
from test_mobcash.user.base_test import BaseAPITestCase

logger = logging.getLogger("mobcash_inte_backend.network")


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
        content = response.content.decode()
        logger.info("Réponse /network : %s", content)

        self.assertEqual(
            response.status_code, status.HTTP_200_OK, f"Échec status : {content}"
        )

        data = response.json()
        if not data:
            self.fail(f"La liste est vide ! Contenu complet : {content}")

        self.assertIsInstance(data, list)
        self.assertIn("id", data[0])
        self.assertIn("name", data[0])
        logger.info("✅ /network renvoie au moins un élément avec 'id' et 'name'")
