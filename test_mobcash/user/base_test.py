import logging
from rest_framework.test import APITestCase
from django.urls import reverse
from rest_framework import status

logger = logging.getLogger("mobcash_inte_backend.auth")


class BaseAPITestCase(APITestCase):
    """
    Classe de base pour les tests :
    - Gère la création de user
    - Gère le login et le stockage du token
    """

    def setUp(self):
        self.registration_url = reverse("auth:registration")
        self.login_url = reverse("auth:login")

        self.user_data = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john1.doe@example.com",
            "phone": "2250700000003",
            "password": "securepassword123",
            "re_password": "securepassword123",
        }

        self.login_data = {
            "email_or_phone": self.user_data["email"],
            "password": self.user_data["password"],
        }

        logger.info("⚙️ Initialisation du BaseAPITestCase")

    def create_user_and_login(self):
        """
        Crée un utilisateur et récupère un token d'accès valide
        """
        logger.info("🧩 Création d’un utilisateur pour le test")
        reg_resp = self.client.post(
            self.registration_url, self.user_data, format="json"
        )
        assert reg_resp.status_code in [
            status.HTTP_200_OK,
            status.HTTP_201_CREATED,
        ], f"Échec création user : {reg_resp.content}"

        logger.info("🔐 Connexion pour obtenir le token")
        login_resp = self.client.post(self.login_url, self.login_data, format="json")
        assert (
            login_resp.status_code == status.HTTP_200_OK
        ), f"Échec login : {login_resp.content}"

        data = login_resp.json()
        token = data.get("access")
        assert token, "Token d’accès manquant dans la réponse de login"

        self.access_token = token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        logger.info("✅ Token défini pour le client de test")
        return token
