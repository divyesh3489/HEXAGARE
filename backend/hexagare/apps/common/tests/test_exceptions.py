from django.test import SimpleTestCase
from rest_framework.exceptions import NotAuthenticated, NotFound, PermissionDenied, ValidationError

from apps.common.exceptions import api_exception_handler


class ApiExceptionHandlerTests(SimpleTestCase):
    def _handle(self, exc):
        return api_exception_handler(exc, {})

    def test_returns_none_for_non_drf_exception(self):
        self.assertIsNone(self._handle(ValueError("boom")))

    def test_validation_error_dict_produces_fields(self):
        response = self._handle(
            ValidationError({"name": ["This field is required."], "qty": ["Must be positive."]})
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "validation_error")
        self.assertEqual(response.data["error"]["message"], "Validation failed.")
        self.assertEqual(
            response.data["error"]["fields"],
            {"name": ["This field is required."], "qty": ["Must be positive."]},
        )

    def test_validation_error_list_uses_non_field_errors(self):
        response = self._handle(ValidationError(["Something is wrong."]))
        self.assertEqual(
            response.data["error"]["fields"], {"non_field_errors": ["Something is wrong."]}
        )

    def test_not_found_has_code_and_message_no_fields(self):
        response = self._handle(NotFound())
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["error"]["code"], "not_found")
        self.assertIn("message", response.data["error"])
        self.assertNotIn("fields", response.data["error"])

    def test_permission_denied_code(self):
        response = self._handle(PermissionDenied())
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"]["code"], "permission_denied")

    def test_not_authenticated_code(self):
        response = self._handle(NotAuthenticated())
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["error"]["code"], "not_authenticated")
