"""
``backend.credential_store`` should be marked deprecated.

The audit recommends migrating callers to the repository-backed
credential service (``backend.repositories.credential_repo``) and
explicitly marking the legacy module-level helpers as deprecated.
This test pins one of two acceptable signals:

1. Importing the module raises ``DeprecationWarning``, OR
2. The module exposes a truthy ``__deprecated__`` flag.

Marked ``xfail`` until the deprecation marker lands.
"""
from __future__ import annotations

import importlib
import sys
import warnings

import pytest

pytestmark = [pytest.mark.security]


@pytest.mark.xfail(
    reason="legacy module not yet marked deprecated",
    strict=False,
)
def test_legacy_credential_store_marked_deprecated() -> None:
    sys.modules.pop("backend.credential_store", None)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        mod = importlib.import_module("backend.credential_store")
    raised = any(
        issubclass(w.category, DeprecationWarning) for w in caught
    )
    flagged = bool(getattr(mod, "__deprecated__", False))
    assert raised or flagged, (
        "backend.credential_store must either raise DeprecationWarning "
        "on import or expose a truthy __deprecated__ flag"
    )
