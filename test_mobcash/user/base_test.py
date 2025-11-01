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

    @classmethod
    def setUpTestData(cls):
        cls.registration_url = reverse("auth:registration")
        cls.login_url = reverse("auth:login")

        cls.user_data = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john1.doe@example.com",
            "phone": "2250700000003",
            "password": "securepassword123",
            "re_password": "securepassword123",
        }

        cls.login_data = {
            "email_or_phone": cls.user_data["email"],
            "password": cls.user_data["password"],
        }

        logger.info("⚙️ Initialisation du BaseAPITestCase (une seule fois)")

        # Création de l'utilisateur et login une seule fois
        cls._create_user_and_login(cls)

    @classmethod
    def _create_user_and_login(cls):
        """
        Crée un utilisateur et récupère un token d'accès valide (exécuté une seule fois)
        """
        logger.info("🧩 Création d’un utilisateur pour le test (setup unique)")
        reg_resp = cls().client.post(cls.registration_url, cls.user_data, format="json")
        assert reg_resp.status_code in [
            status.HTTP_200_OK,
            status.HTTP_201_CREATED,
        ], f"Échec création user : {reg_resp.content}"

        logger.info("🔐 Connexion pour obtenir le token")
        login_resp = cls().client.post(cls.login_url, cls.login_data, format="json")
        assert (
            login_resp.status_code == status.HTTP_200_OK
        ), f"Échec login : {login_resp.content}"

        data = login_resp.json()
        token = data.get("access")
        assert token, "Token d’accès manquant dans la réponse de login"

        cls.access_token = token
        cls.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        logger.info("✅ Token défini pour le client de test")
