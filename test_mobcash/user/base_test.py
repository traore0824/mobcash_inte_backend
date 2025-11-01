import logging
from rest_framework.test import APITestCase
from django.urls import reverse
from rest_framework import status
from django.contrib.auth import get_user_model

logger = logging.getLogger("mobcash_inte_backend.auth")


class BaseAPITestCase(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.registration_url = reverse("auth:registration")
        cls.login_url = reverse("auth:login")

        cls.user_data = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john1.doe@example.com",
            "username": "john1.doe@example.com",  # ⚡ obligatoire pour ton UserManager
            "phone": "2250700000003",
            "password": "securepassword123",
        }

        cls.password = cls.user_data["password"]

        User = get_user_model()
        cls.user = User.objects.create_user(
            username=cls.user_data["username"],
            email=cls.user_data["email"],
            phone=cls.user_data["phone"],
            first_name=cls.user_data["first_name"],
            last_name=cls.user_data["last_name"],
            password=cls.password,
        )
        logger.info("✅ Utilisateur créé en DB (setup unique)")

    def setUp(self):
        self.login_data = {
            "email_or_phone": self.user.email,
            "password": self.password,
        }

        login_resp = self.client.post(self.login_url, self.login_data, format="json")
        
        assert (
            login_resp.status_code == status.HTTP_200_OK
        ), f"Échec login : {login_resp.content}"

        token = login_resp.json().get("access")
        assert token, "Token d’accès manquant dans la réponse de login"

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        logger.info("✅ Token défini pour le client de test")
