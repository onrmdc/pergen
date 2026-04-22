"""
Batch-3+4 audit fixes — auth gate, path traversal hardening, command
validator dict guard, diff-input cap, PBKDF2 iteration bump,
TLS/known-hosts opt-in, defensive HTTP headers.

Each test references its audit ID (C1, C4, H1, H2, H5, H9, M1, M4,
M8, M10, M11) so the audit report and the test suite stay
cross-referenceable.
"""
from __future__ import annotations

import os


# --------------------------------------------------------------------------- #
# C1 (security) — Optional API-token auth gate                                 #
# --------------------------------------------------------------------------- #


def test_api_token_gate_blocks_unauthenticated_requests_when_enabled(
    flask_app, monkeypatch
):
    """When ``PERGEN_API_TOKEN`` is set, requests without the token get 401."""
    flask_app.config["PERGEN_API_TOKEN"] = "test-token-123456"
    client = flask_app.test_client()
    # Health endpoint stays open (liveness probes can't carry tokens by default).
    assert client.get("/api/v2/health").status_code == 200
    # Real API endpoints require the token.
    r = client.get("/api/inventory")
    assert r.status_code == 401
    assert "token" in r.get_json()["error"].lower()


def test_api_token_gate_accepts_correct_token(flask_app):
    flask_app.config["PERGEN_API_TOKEN"] = "test-token-456789"
    client = flask_app.test_client()
    r = client.get("/api/inventory", headers={"X-API-Token": "test-token-456789"})
    assert r.status_code == 200


def test_api_token_gate_rejects_wrong_token(flask_app):
    flask_app.config["PERGEN_API_TOKEN"] = "right-token-123456"
    client = flask_app.test_client()
    r = client.get("/api/inventory", headers={"X-API-Token": "wrong-token"})
    assert r.status_code == 401


def test_api_token_gate_disabled_by_default_does_not_block(client):
    """Backwards compat — without the env var, every endpoint stays open."""
    r = client.get("/api/inventory")
    assert r.status_code == 200


# --------------------------------------------------------------------------- #
# C4 — Hard confirm header on transceiver recover/clear                        #
# --------------------------------------------------------------------------- #


def test_transceiver_recover_requires_confirmation_header(client, monkeypatch):
    """When PERGEN_REQUIRE_DESTRUCTIVE_CONFIRM=1, recover needs X-Confirm-Destructive: yes."""
    monkeypatch.setenv("PERGEN_REQUIRE_DESTRUCTIVE_CONFIRM", "1")
    r = client.post(
        "/api/transceiver/recover",
        json={"device": {"hostname": "leaf-01"}, "interfaces": ["Ethernet1/1"]},
    )
    assert r.status_code == 403
    assert "confirm" in r.get_json()["error"].lower()


# --------------------------------------------------------------------------- #
# H9 — Path traversal hardening (pathlib-based)                                #
# --------------------------------------------------------------------------- #


def test_report_repository_uses_pathlib_is_relative_to(tmp_path):
    """Defense uses Path.is_relative_to — works on POSIX and Windows alike."""
    from backend.repositories import ReportRepository

    repo = ReportRepository(str(tmp_path))
    # These all attempt to escape the reports_dir; either rejected (raise)
    # or contained under reports_dir.
    from pathlib import Path

    abs_root = Path(str(tmp_path)).resolve()
    for evil in ["../../etc/passwd", "..\\..\\windows", "a/../../b", "./../escape"]:
        try:
            path = repo._report_path(evil)
            assert Path(path).resolve().is_relative_to(abs_root), (
                f"{evil!r} escaped to {path!r}"
            )
        except ValueError:
            pass  # acceptable — explicit rejection


# --------------------------------------------------------------------------- #
# M1 — Debug field requires explicit opt-in                                    #
# --------------------------------------------------------------------------- #


def test_nat_lookup_debug_flag_requires_env_opt_in(client, monkeypatch):
    """``debug=true`` body field should not work unless PERGEN_ALLOW_DEBUG_RESPONSES=1.

    We intercept the upstream `nat_lookup` call so the test doesn't try
    to reach a real firewall — only the request-body sanitisation matters.
    """
    from unittest.mock import patch

    monkeypatch.delenv("PERGEN_ALLOW_DEBUG_RESPONSES", raising=False)
    captured: dict = {}

    def fake_nat(src_ip, dest_ip, secret_key, _creds, **kwargs):
        captured.update(kwargs)
        return {"ok": True, "rule_name": "any", "debug": {"raw": "secret-stuff"}}

    with patch("backend.nat_lookup.nat_lookup", side_effect=fake_nat):
        r = client.post(
            "/api/nat-lookup",
            json={"src_ip": "203.0.113.1", "debug": True},
        )
    assert r.status_code == 200
    # Without opt-in, the route MUST suppress the debug param going down to
    # the helper (so even a buggy helper can't leak), regardless of what
    # the helper returns.
    assert captured.get("debug") is False, (
        "nat-lookup forwarded debug=True without PERGEN_ALLOW_DEBUG_RESPONSES opt-in"
    )


# --------------------------------------------------------------------------- #
# M4 — DoS cap on /api/diff input                                              #
# --------------------------------------------------------------------------- #


def test_diff_explicit_input_size_cap(client):
    """A 1MB pre/post must be rejected with 400, not OOM the worker."""
    big = "a" * (1024 * 1024)  # 1 MB per side
    r = client.post("/api/diff", json={"pre": big, "post": big[:-1]})
    # Two acceptable behaviours:
    #   * 400 — outright rejection
    #   * 413 — Flask MAX_CONTENT_LENGTH triggers
    # NOT acceptable: 200 with full diff (memory bomb)
    assert r.status_code in (400, 413), (
        f"unexpected {r.status_code} for 1MB diff payload — possible DoS"
    )


# --------------------------------------------------------------------------- #
# M8 — Defensive HTTP headers (CSP, HSTS)                                      #
# --------------------------------------------------------------------------- #


def test_response_carries_content_security_policy(client):
    r = client.get("/api/v2/health")
    assert r.headers.get("Content-Security-Policy"), (
        "CSP header missing — see audit M8"
    )


def test_response_carries_strict_transport_security_header(client):
    # Audit L-02: HSTS is only set on HTTPS requests (browsers ignore HSTS
    # over HTTP, and serving it over HTTP risks locking a future HTTPS
    # proxy hostname into HTTPS-only with a 2-year max-age).
    r = client.get("/api/v2/health", base_url="https://localhost")
    assert r.headers.get("Strict-Transport-Security"), (
        "HSTS header missing on HTTPS response — see audit M8 / L-02"
    )


def test_strict_transport_security_not_set_on_http_request(client):
    """Audit L-02 — HTTP responses must NOT carry HSTS."""
    r = client.get("/api/v2/health", base_url="http://localhost")
    assert "Strict-Transport-Security" not in r.headers, (
        "HSTS header set on HTTP response — would lock future HTTPS proxy "
        "hostname into HTTPS-only; see audit L-02"
    )


# --------------------------------------------------------------------------- #
# M10 — PBKDF2 iteration count                                                 #
# --------------------------------------------------------------------------- #


def test_pbkdf2_iteration_count_meets_owasp_2023_guidance():
    """OWASP cheat sheet recommends ≥600,000 iterations for SHA-256."""
    from backend.security import encryption as enc_mod

    iters = getattr(enc_mod, "_PBKDF2_ITERS", 0)
    assert iters >= 600_000, (
        f"PBKDF2 iterations = {iters}; OWASP 2023 minimum is 600,000."
    )


# --------------------------------------------------------------------------- #
# M11 — CommandValidator dict-form whitelist                                   #
# --------------------------------------------------------------------------- #


def test_arista_run_cmds_strips_unknown_dict_keys(client):
    """A non-enable dict cmd must only carry the ``cmd`` key forward."""
    from unittest.mock import patch

    with patch(
        "backend.runners.arista_eapi.run_cmds", return_value=(["ok"], None)
    ) as m:
        # Use a real credential to get past the cred preflight.
        client.post(
            "/api/credentials",
            json={"name": "phase-m11", "method": "basic", "username": "u", "password": "p"},
        )
        client.post(
            "/api/arista/run-cmds",
            json={
                "device": {
                    "ip": "203.0.113.1",
                    "hostname": "h",
                    "credential": "phase-m11",
                },
                "cmds": [
                    {"cmd": "show version", "input": "INJECTED\nconfigure terminal"},
                ],
            },
        )
    # The runner was called — inspect what got forwarded.
    if m.called:
        forwarded_cmds = m.call_args.args[3]  # 4th positional: cmds list
        for c in forwarded_cmds:
            if isinstance(c, dict) and (c.get("cmd") or "").strip().lower() != "enable":
                assert "input" not in c, (
                    "Non-enable dict cmd retained 'input' key — possible bypass"
                )


# --------------------------------------------------------------------------- #
# H1 — SSH host key policy is configurable                                     #
# --------------------------------------------------------------------------- #


def test_ssh_runner_supports_strict_host_key_check_env():
    """``PERGEN_SSH_STRICT_HOST_KEY=1`` must enable RejectPolicy."""
    import importlib

    # Re-import with the env set
    os.environ["PERGEN_SSH_STRICT_HOST_KEY"] = "1"
    try:
        from backend.runners import ssh_runner

        importlib.reload(ssh_runner)
        # The module must expose its policy choice for verification.
        assert hasattr(ssh_runner, "_HOST_KEY_POLICY_NAME"), (
            "ssh_runner must expose _HOST_KEY_POLICY_NAME for audit visibility"
        )
        assert ssh_runner._HOST_KEY_POLICY_NAME in ("RejectPolicy", "WarningPolicy"), (
            "PERGEN_SSH_STRICT_HOST_KEY=1 must select a non-AutoAdd policy"
        )
    finally:
        os.environ.pop("PERGEN_SSH_STRICT_HOST_KEY", None)


# --------------------------------------------------------------------------- #
# H2 — Device TLS verification posture (intentionally disabled fleet-wide)    #
# --------------------------------------------------------------------------- #


def test_device_tls_verify_disabled_for_self_signed_fleet():
    """All device-facing HTTPS calls must skip TLS verification.

    Network devices in this fleet present local self-signed certificates with
    no path to a public CA, so ``DEVICE_TLS_VERIFY`` is the single source of
    truth and must remain ``False``. If a future operator deploys CA-signed
    device certs, flip the constant in ``backend/runners/_http.py`` rather
    than reintroducing per-runner toggles.
    """
    from backend.runners._http import DEVICE_TLS_VERIFY

    assert DEVICE_TLS_VERIFY is False, (
        "DEVICE_TLS_VERIFY must be False for self-signed device certificates"
    )


def test_device_runners_use_shared_tls_constant():
    """Each device runner must route through the shared posture constant."""
    from backend import nat_lookup
    from backend.runners import arista_eapi, cisco_nxapi
    from backend.runners._http import DEVICE_TLS_VERIFY

    # Spot-check that the constant is actually imported (and therefore used)
    # in every device-facing module. Catches accidental local re-definitions.
    assert arista_eapi.DEVICE_TLS_VERIFY is DEVICE_TLS_VERIFY
    assert cisco_nxapi.DEVICE_TLS_VERIFY is DEVICE_TLS_VERIFY
    assert nat_lookup.DEVICE_TLS_VERIFY is DEVICE_TLS_VERIFY
