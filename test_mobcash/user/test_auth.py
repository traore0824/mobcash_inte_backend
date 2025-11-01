from rest_framework import status
import logging
from .base_test import BaseAPITestCase

logger = logging.getLogger("mobcash_inte_backend.auth")


class AuthTests(BaseAPITestCase):
    """Tests spécifiques pour AUTH"""

    def test_registration(self):
        response = self.client.post(
            self.registration_url, self.user_data, format="json"
        )
        logger.info("Réponse registration : %s", response.content)

        self.assertIn(
            response.status_code, [status.HTTP_200_OK, status.HTTP_201_CREATED]
        )
        data = response.json()
        self.assertIn("id", data)
        self.assertEqual(data["email"], self.user_data["email"])
        logger.info("✅ Registration OK pour %s", data["email"])

    def test_login(self):
        register_response= self.client.post(self.registration_url, self.user_data, format="json")
        print(register_response.status_code, register_response.content)
        response = self.client.post(self.login_url, self.login_data, format="json")
        logger.debug("Réponse login : %s", response.content)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("access", data)
        logger.info("✅ Login OK pour %s", self.login_data["email_or_phone"])
