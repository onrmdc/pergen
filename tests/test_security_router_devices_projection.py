"""
``/api/router-devices`` must not expose the credential field.

The inventory carries a ``credential`` column that names a stored
credential (used server-side to look up encrypted username/password).
While the value is just a name (not the secret itself), leaking it to
unauthenticated SPA callers tells an attacker which credential bucket
to target. The route must project devices to non-credential fields.

Marked ``xfail`` until the route adds an explicit field projection —
the current implementation returns the raw inventory rows.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.security]


def test_router_devices_response_omits_credential_field(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The default mock inventory has no DCI/WAN routers, so we'd get an
    # empty list and trivially pass. Build a one-router inventory so the
    # assertion has something to bite on.
    csv = tmp_path / "router-inv.csv"
    csv.write_text(
        "hostname,ip,fabric,site,hall,vendor,model,role,tag,credential\n"
        "dci-01,10.1.0.1,FAB1,Mars,Hall-1,Arista,EOS,DCI-Router,,test-cred\n"
        "wan-01,10.1.0.2,FAB1,Mars,Hall-1,Arista,EOS,WAN-Router,,test-cred\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PERGEN_INVENTORY_PATH", str(csv))
    monkeypatch.setenv("PERGEN_INSTANCE_DIR", str(tmp_path / "instance"))
    (tmp_path / "instance").mkdir(exist_ok=True)

    import importlib
    import sys

    for mod in [
        "backend.app",
        "backend.app_factory",
        "backend.config",
        "backend.config.settings",
        "backend.inventory.loader",
    ]:
        sys.modules.pop(mod, None)
    factory = importlib.import_module("backend.app_factory")
    app = factory.create_app("testing")
    app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=True)
    client = app.test_client()

    r = client.get("/api/router-devices?scope=all")
    assert r.status_code == 200
    body = r.get_json() or {}
    devices = body.get("devices") or []
    assert devices, "expected at least one DCI/WAN router from the seeded inventory"
    offenders = [d for d in devices if isinstance(d, dict) and "credential" in d]
    assert not offenders, (
        f"/api/router-devices leaks credential field on {len(offenders)} device(s); "
        f"first offender: {offenders[0]!r}"
    )
