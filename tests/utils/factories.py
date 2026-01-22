from __future__ import annotations

from types import SimpleNamespace


def make_user(email: str = "user@example.com", admin: bool = False) -> SimpleNamespace:
    return SimpleNamespace(id=1, email=email, admin=admin, full_name="Test User")
