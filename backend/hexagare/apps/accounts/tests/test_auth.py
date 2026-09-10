from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APITestCase

from apps.accounts.models import LoginHistory

User = get_user_model()

PW = "correct-horse-8-battery"
LOGIN = "/api/v1/auth/login/"
REFRESH = "/api/v1/auth/refresh/"
LOGOUT = "/api/v1/auth/logout/"
PROFILE = "/api/v1/auth/profile/"
PW_CHANGE = "/api/v1/auth/password/change/"
PW_RESET = "/api/v1/auth/password/reset/"
PW_RESET_CONFIRM = "/api/v1/auth/password/reset/confirm/"


class AuthFlowTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("worker@hexagare.test", PW, first_name="Wanda")

    def _login(self, email="worker@hexagare.test", password=PW):
        return self.client.post(LOGIN, {"email": email, "password": password}, format="json")

    def _auth(self, access):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    # -- login -----------------------------------------------------------
    def test_login_success_returns_tokens_and_user(self):
        response = self._login()
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["user"]["email"], "worker@hexagare.test")
        self.assertIn("roles", response.data["user"])
        self.assertIn("permissions", response.data["user"])
        self.assertTrue(
            LoginHistory.objects.filter(
                user=self.user, event=LoginHistory.Event.LOGIN_SUCCESS
            ).exists()
        )

    def test_login_wrong_password_is_401_enveloped_and_recorded(self):
        response = self._login(password="nope")
        self.assertEqual(response.status_code, 401)
        self.assertIn("error", response.data)
        self.assertIn("code", response.data["error"])
        self.assertIn("message", response.data["error"])
        entry = LoginHistory.objects.filter(event=LoginHistory.Event.LOGIN_FAILED).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.email_attempted, "worker@hexagare.test")
        self.assertIsNone(entry.user)

    def test_login_missing_fields_is_validation_envelope(self):
        response = self.client.post(LOGIN, {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "validation_error")
        self.assertIn("fields", response.data["error"])

    # -- refresh / logout ---------------------------------------------
    def test_refresh_issues_new_access(self):
        refresh = self._login().data["refresh"]
        response = self.client.post(REFRESH, {"refresh": refresh}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)

    def test_logout_blacklists_refresh(self):
        tokens = self._login().data
        self._auth(tokens["access"])
        response = self.client.post(LOGOUT, {"refresh": tokens["refresh"]}, format="json")
        self.assertEqual(response.status_code, 205)
        self.assertTrue(
            LoginHistory.objects.filter(
                user=self.user, event=LoginHistory.Event.LOGOUT
            ).exists()
        )
        self.client.credentials()
        reused = self.client.post(REFRESH, {"refresh": tokens["refresh"]}, format="json")
        self.assertEqual(reused.status_code, 401)

    # -- profile ----------------------------------------------------
    def test_profile_get(self):
        self._auth(self._login().data["access"])
        response = self.client.get(PROFILE)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["email"], "worker@hexagare.test")
        self.assertEqual(response.data["first_name"], "Wanda")
        self.assertIn("roles", response.data)

    def test_profile_update_returns_full_representation(self):
        self._auth(self._login().data["access"])
        response = self.client.patch(
            PROFILE, {"first_name": "Wendy", "phone": "+91-99999-11111"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["first_name"], "Wendy")
        self.assertEqual(response.data["phone"], "+91-99999-11111")
        self.assertIn("permissions", response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Wendy")

    def test_profile_requires_auth(self):
        self.assertEqual(self.client.get(PROFILE).status_code, 401)

    # -- password change ------------------------------------------
    def test_password_change(self):
        self._auth(self._login().data["access"])
        new_pw = "N3w-Sekrit-phrase-77"
        response = self.client.post(
            PW_CHANGE, {"old_password": PW, "new_password": new_pw}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.client.credentials()
        self.assertEqual(self._login(password=PW).status_code, 401)
        self.assertEqual(self._login(password=new_pw).status_code, 200)

    def test_password_change_wrong_old_password(self):
        self._auth(self._login().data["access"])
        response = self.client.post(
            PW_CHANGE,
            {"old_password": "wrong", "new_password": "N3w-Sekrit-phrase-77"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("old_password", response.data["error"]["fields"])

    # -- password reset -----------------------------------------
    def test_password_reset_request_sends_email_for_known_user(self):
        response = self.client.post(PW_RESET, {"email": "worker@hexagare.test"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("worker@hexagare.test", mail.outbox[0].to)

    def test_password_reset_request_is_silent_for_unknown_user(self):
        response = self.client.post(PW_RESET, {"email": "ghost@hexagare.test"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_password_reset_confirm(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        new_pw = "Reset-phrase-abc-42"
        response = self.client.post(
            PW_RESET_CONFIRM,
            {"uid": uid, "token": token, "new_password": new_pw},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._login(password=new_pw).status_code, 200)

    def test_password_reset_confirm_rejects_bad_token(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        response = self.client.post(
            PW_RESET_CONFIRM,
            {"uid": uid, "token": "bad-token", "new_password": "Reset-phrase-abc-42"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
