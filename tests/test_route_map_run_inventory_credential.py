"""
Wave-7.9 — ``/api/route-map/run`` resolves credential from inventory.

Operator-reported bug 2026-04-23: the DCI/WAN router page produced
``"no credential for ''"`` errors for every device, even though the
inventory CSV had ``credential=tyc`` populated and the credential was
saved in the credentials store. The empty string between the quotes
was the giveaway: the route was reading ``credential`` from the
**request body**, not from the inventory.

Cause
-----
``/api/router-devices`` deliberately strips the ``credential`` field
from the device list it returns to the SPA (audit / projection: do
not leak credential names to unauthenticated callers). Its docstring
promises that ``/api/route-map/run`` will re-resolve the credential
from inventory by hostname. That promise was never implemented —
the route still does ``cred_name = (d.get("credential") or "").strip()``
on the request-body payload, which is always empty since wave-3.

Fix
---
Mirror the audit H-2 pattern already used by ``transceiver_bp`` and
the other routes in ``device_commands_bp``: call
``_resolve_inventory_device(d)`` to bind the request device to its
canonical inventory row, then read the credential from THAT row.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture()
def router_inventory_csv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Inventory with one Arista DCI router that has a credential set.

    Wave-7.9 regression scenario: the SPA sends the device payload
    WITHOUT a credential field (per /api/router-devices' projection),
    and the route must still resolve the credential from this CSV.
    """
    csv_path = tmp_path / "inventory.csv"
    csv_path.write_text(
        "hostname,ip,fabric,site,hall,vendor,model,role,tag,credential\n"
        "DCIRTR-IL2-H2-R217-WED-P0-N01,10.32.0.35,tyc,Mars,hall-2,arista,eos,dci-router,do-not-search,tyc\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PERGEN_INVENTORY_PATH", str(csv_path))
    return csv_path


@pytest.fixture()
def router_app(router_inventory_csv: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Build a fresh app pointed at the router inventory CSV.

    Mirrors the conftest's ``flask_app`` fixture eviction set so the
    blueprint modules pick up our env-driven CSV / instance dir
    instead of the previous test's. Without this exhaustive eviction
    the device_commands_bp module retains a binding to the previous
    ``backend.credential_store`` module from the prior test, and the
    legacy fall-through bridge looks at the wrong tmp dir.
    """
    import importlib
    import sys

    monkeypatch.setenv("PERGEN_INSTANCE_DIR", str(tmp_path / "instance"))
    monkeypatch.setenv("PERGEN_DEV_OPEN_API", "1")
    # Evict the same cached app modules conftest's flask_app does — this
    # is the curated list that survives env changes between tests.
    for mod in [
        "backend.app",
        "backend.app_factory",
        "backend.blueprints",
        "backend.blueprints.bgp_bp",
        "backend.blueprints.commands_bp",
        "backend.blueprints.credentials_bp",
        "backend.blueprints.device_commands_bp",
        "backend.blueprints.health_bp",
        "backend.blueprints.inventory_bp",
        "backend.blueprints.network_lookup_bp",
        "backend.blueprints.network_ops_bp",
        "backend.blueprints.notepad_bp",
        "backend.blueprints.reports_bp",
        "backend.blueprints.runs_bp",
        "backend.blueprints.transceiver_bp",
        "backend.config",
        "backend.config.settings",
        "backend.config.commands_loader",
        "backend.config.app_config",
        "backend.inventory.loader",
        "backend.credential_store",
    ]:
        sys.modules.pop(mod, None)
    factory_mod = importlib.import_module("backend.app_factory")
    return factory_mod.create_app("development")


@pytest.fixture()
def router_client(router_app):
    return router_app.test_client()


def _seed_credential(app, name: str = "tyc") -> None:
    """Save a basic credential under ``name`` in the v2 store so the
    legacy fall-through bridge can find it.
    """
    cred_svc = app.extensions["credential_service"]
    cred_svc.set(name, method="basic", username="user", password="pw")


# --------------------------------------------------------------------------- #
# Regression tests                                                            #
# --------------------------------------------------------------------------- #


def test_route_map_run_resolves_credential_from_inventory_when_body_omits_it(
    router_app, router_client
):
    """The wave-7.9 fix: when the SPA sends only hostname+ip (no
    credential field), the route must look up the credential by
    hostname from the inventory and use THAT — not the empty body
    value.
    """
    _seed_credential(router_app, "tyc")

    # Mimic exactly what the SPA sends post-wave-3 projection:
    # the credential field is intentionally absent.
    body = {
        "devices": [
            {
                "hostname": "DCIRTR-IL2-H2-R217-WED-P0-N01",
                "ip": "10.32.0.35",
                "vendor": "arista",
                "model": "eos",
                # NOTE: no "credential" key — that's the bug-trigger.
            }
        ]
    }

    # Stub the eAPI call so we don't actually hit the network. We only
    # care that we got PAST the credential-resolution gate.
    with patch(
        "backend.runners.arista_eapi.run_commands",
        return_value=([{"hostname": "test"}], None),
    ) as mock_eapi:
        r = router_client.post("/api/route-map/run", json=body)

    assert r.status_code == 200
    data = r.get_json()
    # The error envelope must NOT contain a "no credential for ''" entry.
    cred_errs = [
        e for e in data.get("errors", [])
        if "no credential for ''" in (e.get("error") or "")
    ]
    assert cred_errs == [], (
        "wave-7.9 regression: route resolved credential from request body "
        "instead of from inventory. Errors: " + str(data.get("errors"))
    )
    # And eAPI must have been called with the resolved username/password
    # (proves we got all the way through the gate).
    assert mock_eapi.called, (
        "credential resolved but eAPI was never called — route logic broke"
    )
    # The username we seeded was "user"; the call signature is
    # (ip, username, password, commands, ...).
    call_args = mock_eapi.call_args[0]
    assert call_args[1] == "user", f"expected username=user, got {call_args[1]!r}"
    assert call_args[2] == "pw", f"expected password=pw, got {call_args[2]!r}"


def test_route_map_run_returns_friendly_error_for_unknown_hostname(
    router_app, router_client
):
    """Sanity: if the request body names a hostname that is NOT in the
    inventory, the route must return a clear 'device not found in
    inventory' error — NOT 'no credential for' (which would mask the
    real cause).
    """
    body = {
        "devices": [
            {
                "hostname": "TOTALLY-FAKE-DEVICE",
                "ip": "192.0.2.99",
                "vendor": "arista",
                "model": "eos",
            }
        ]
    }
    r = router_client.post("/api/route-map/run", json=body)
    assert r.status_code == 200
    data = r.get_json()
    errs = data.get("errors") or []
    assert errs, "expected at least one error for unknown device"
    # Must mention inventory, not credential.
    msg = errs[0].get("error", "").lower()
    assert "inventory" in msg or "not found" in msg, (
        f"expected an inventory-not-found error, got: {msg!r}"
    )
    assert "no credential for ''" not in errs[0].get("error", ""), (
        "must not return a misleading 'no credential' for an unknown device"
    )


def test_route_map_run_does_not_trust_credential_from_request_body(
    router_app, router_client
):
    """Audit H-2 invariant: even if the request body PROVIDES a
    ``credential`` field, the route must IGNORE it and resolve from
    inventory. Otherwise an attacker could supply a forged credential
    name and probe the credential store.

    The inventory device's credential is "tyc"; we send "evil-cred"
    in the body. The route must resolve "tyc" from inventory and use
    that — it must NOT look up "evil-cred".
    """
    _seed_credential(router_app, "tyc")

    body = {
        "devices": [
            {
                "hostname": "DCIRTR-IL2-H2-R217-WED-P0-N01",
                "ip": "10.32.0.35",
                "vendor": "arista",
                "model": "eos",
                "credential": "evil-cred",  # attacker-supplied, must be ignored
            }
        ]
    }

    with patch(
        "backend.runners.arista_eapi.run_commands",
        return_value=([{"hostname": "test"}], None),
    ) as mock_eapi:
        r = router_client.post("/api/route-map/run", json=body)

    assert r.status_code == 200
    data = r.get_json()
    cred_errs = [
        e for e in data.get("errors", [])
        if "no credential for 'evil-cred'" in (e.get("error") or "")
    ]
    assert cred_errs == [], (
        "audit H-2 violation: route looked up the request-body credential "
        "name 'evil-cred' instead of resolving from inventory. Errors: "
        + str(data.get("errors"))
    )
    # eAPI must have been called with the credential resolved from the
    # inventory ("tyc" → username=user / password=pw), NOT evil-cred.
    assert mock_eapi.called, (
        f"eAPI never called; full response = {data!r}"
    )
    call_args = mock_eapi.call_args[0]
    assert call_args[1] == "user"
    assert call_args[2] == "pw"
