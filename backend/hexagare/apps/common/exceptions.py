"""Global DRF exception handling.

Every error response from the API is normalised to a single envelope::

    {"error": {"code": "<machine_code>", "message": "<human message>", "fields"?: {...}}}

``fields`` is present only for validation errors and maps each field name (or
``non_field_errors``) to a list of message strings.

Wire this up via ``REST_FRAMEWORK["EXCEPTION_HANDLER"]``.
"""

from __future__ import annotations

from rest_framework import exceptions as drf_exceptions
from rest_framework.views import exception_handler as drf_exception_handler


def _as_message_list(value) -> list[str]:
    """Coerce an arbitrary DRF error value into a flat list of strings."""
    if isinstance(value, list):
        messages: list[str] = []
        for item in value:
            if isinstance(item, dict):
                messages.extend(_as_message_list(list(item.values())))
            elif isinstance(item, list):
                messages.extend(_as_message_list(item))
            else:
                messages.append(str(item))
        return messages
    if isinstance(value, dict):
        messages = []
        for key, item in value.items():
            messages.extend(f"{key}: {msg}" for msg in _as_message_list(item))
        return messages
    return [str(value)]


def _flatten_validation(data) -> dict[str, list[str]]:
    if isinstance(data, dict):
        return {key: _as_message_list(value) for key, value in data.items()}
    return {"non_field_errors": _as_message_list(data)}


def api_exception_handler(exc, context):
    """DRF ``EXCEPTION_HANDLER`` that returns the Hexagare error envelope."""
    response = drf_exception_handler(exc, context)
    if response is None:
        # Not a DRF-handled exception - let Django produce the 500.
        return None

    code = getattr(exc, "default_code", None) or "error"
    fields: dict[str, list[str]] | None = None

    if isinstance(exc, drf_exceptions.ValidationError):
        code = "validation_error"
        message = "Validation failed."
        fields = _flatten_validation(response.data)
    elif isinstance(response.data, dict) and "detail" in response.data:
        detail = response.data["detail"]
        message = str(detail)
        code = getattr(detail, "code", code) or code
    else:
        messages = _as_message_list(response.data)
        message = messages[0] if messages else "An error occurred."

    envelope: dict = {"error": {"code": code, "message": message}}
    if fields:
        envelope["error"]["fields"] = fields

    response.data = envelope
    return response
