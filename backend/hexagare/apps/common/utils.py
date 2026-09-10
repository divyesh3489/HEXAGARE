"""Small cross-cutting request helpers."""

from __future__ import annotations


def get_client_ip(request) -> str | None:
    """Best-effort client IP: first ``X-Forwarded-For`` hop, else ``REMOTE_ADDR``.

    Trust ``X-Forwarded-For`` only because staging/production sit behind a
    known load balancer (see ``production.py``'s ``SECURE_PROXY_SSL_HEADER``).
    """
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def get_user_agent(request) -> str:
    return request.META.get("HTTP_USER_AGENT", "")
