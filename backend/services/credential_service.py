"""
``CredentialService`` — façade over the credential repository with
``InputSanitizer`` validation on credential names.

Names are accepted from end users (UI form submission, JSON body) and
ultimately become foreign keys into the inventory CSV — they MUST be
sanitised before any DB write.  Centralising that check here ensures
no route can bypass the sanitiser.
"""
from __future__ import annotations

from backend.repositories import CredentialRepository
from backend.security import InputSanitizer


class CredentialService:
    """Validated credential CRUD."""

    def __init__(self, credential_repo: CredentialRepository) -> None:
        self._repo = credential_repo

    def list(self) -> list[dict]:
        return self._repo.list()

    def get(self, name: str) -> dict | None:
        return self._repo.get(name)

    def set(
        self,
        name: str,
        *,
        method: str,
        api_key: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        """Sanitise ``name`` then delegate to the repository."""
        ok, cleaned = InputSanitizer.sanitize_credential_name(name)
        if not ok:
            raise ValueError(f"invalid credential name: {cleaned}")
        self._repo.set(
            cleaned,
            method=method,
            api_key=api_key,
            username=username,
            password=password,
        )

    def delete(self, name: str) -> bool:
        """Sanitise ``name`` then delegate to the repository.

        Audit H-4: previously ``delete`` skipped the sanitiser, allowing
        log-injection / control-byte names to slip through. Mirror
        ``set()`` so every mutation path is uniform.
        """
        ok, cleaned = InputSanitizer.sanitize_credential_name(name)
        if not ok:
            return False
        return self._repo.delete(cleaned)
