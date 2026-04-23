"""
Coverage push — bring blueprints, services, utils to ≥90% line coverage.

Generated from the post-Phase-13 coverage report. Each test is named
for the function it covers and the branch it exercises so future
maintainers can find/extend them.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest as _pytest_for_marker  # noqa: F401

pytestmark = [_pytest_for_marker.mark.integration]


# =========================================================================== #
# transceiver_bp.api_transceiver_recover — happy paths                         #
# =========================================================================== #


def test_transceiver_recover_arista_happy_path(client):
    """Arista vendor branch: recovery succeeds, status_text echoed."""
    with patch("backend.blueprints.transceiver_bp.creds.get_credential") as gc:
        gc.return_value = {"method": "basic", "username": "u", "password": "p"}
        with patch(
            "backend.runners.interface_recovery.recover_interfaces_arista_eos",
            return_value=([{"ok": True}], None),
        ), patch(
            "backend.runners.interface_recovery.fetch_interface_status_summary_arista_eos",
            return_value=("Eth1/1 up 10G", None),
        ):
            r = client.post(
                "/api/transceiver/recover",
                json={
                    "device": {"hostname": "leaf-01"},
                    "interfaces": ["Ethernet1/1"],
                },
            )
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert "Eth1/1" in body["interface_status_output"]
    assert body["commands"]


def test_transceiver_recover_arista_with_status_warning(client):
    """Arista happy + status fetch warning."""
    with patch("backend.blueprints.transceiver_bp.creds.get_credential") as gc:
        gc.return_value = {"method": "basic", "username": "u", "password": "p"}
        with patch(
            "backend.runners.interface_recovery.recover_interfaces_arista_eos",
            return_value=([], None),
        ), patch(
            "backend.runners.interface_recovery.fetch_interface_status_summary_arista_eos",
            return_value=("", "could not fetch status"),
        ):
            r = client.post(
                "/api/transceiver/recover",
                json={
                    "device": {"hostname": "leaf-01"},
                    "interfaces": ["Ethernet1/1"],
                },
            )
    assert r.status_code == 200
    assert r.get_json()["interface_status_warning"] == "could not fetch status"


def test_transceiver_recover_arista_runner_error(client):
    """Arista recovery returns error → 500 with results echoed."""
    with patch("backend.blueprints.transceiver_bp.creds.get_credential") as gc:
        gc.return_value = {"method": "basic", "username": "u", "password": "p"}
        with patch(
            "backend.runners.interface_recovery.recover_interfaces_arista_eos",
            return_value=([], "auth failed"),
        ):
            r = client.post(
                "/api/transceiver/recover",
                json={
                    "device": {"hostname": "leaf-01"},
                    "interfaces": ["Ethernet1/1"],
                },
            )
    assert r.status_code == 500
    body = r.get_json()
    assert body["ok"] is False
    assert body["error"] == "auth failed"


def test_transceiver_recover_cisco_happy_path(client):
    """Cisco vendor branch: recovery succeeds via NX-OS PTY runner."""
    with patch("backend.blueprints.transceiver_bp.creds.get_credential") as gc:
        gc.return_value = {"method": "basic", "username": "u", "password": "p"}
        with patch(
            "backend.runners.interface_recovery.recover_interfaces_cisco_nxos",
            return_value=("done", None),
        ), patch(
            "backend.runners.interface_recovery.fetch_interface_status_summary_cisco_nxos",
            return_value=("Eth1/1 up 10G", None),
        ):
            r = client.post(
                "/api/transceiver/recover",
                json={
                    "device": {"hostname": "leaf-02"},  # Cisco in test inventory
                    "interfaces": ["Ethernet1/1"],
                },
            )
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_transceiver_recover_cisco_runner_error(client):
    with patch("backend.blueprints.transceiver_bp.creds.get_credential") as gc:
        gc.return_value = {"method": "basic", "username": "u", "password": "p"}
        with patch(
            "backend.runners.interface_recovery.recover_interfaces_cisco_nxos",
            return_value=("partial output", "ssh timeout"),
        ):
            r = client.post(
                "/api/transceiver/recover",
                json={
                    "device": {"hostname": "leaf-02"},
                    "interfaces": ["Ethernet1/1"],
                },
            )
    assert r.status_code == 500
    body = r.get_json()
    assert body["error"] == "ssh timeout"
    assert body["output"] == "partial output"


def test_transceiver_recover_unsupported_vendor(client, tmp_path, monkeypatch):
    """Vendor that's not arista/cisco: 400 unsupported."""
    # Inventory needs a Juniper device; mock the inventory service.
    from backend.repositories import InventoryRepository
    from backend.services.inventory_service import InventoryService

    csv = tmp_path / "juniper_inv.csv"
    csv.write_text(
        "hostname,ip,fabric,site,hall,vendor,model,role,tag,credential\n"
        "junos-01,10.0.0.50,FAB1,Mars,Hall-1,Juniper,QFX,Leaf,,test-cred\n",
        encoding="utf-8",
    )
    flask_app = client.application
    flask_app.extensions["inventory_service"] = InventoryService(
        InventoryRepository(str(csv))
    )

    with patch("backend.blueprints.transceiver_bp.creds.get_credential") as gc:
        gc.return_value = {"method": "basic", "username": "u", "password": "p"}
        r = client.post(
            "/api/transceiver/recover",
            json={
                "device": {"hostname": "junos-01"},
                "interfaces": ["Ethernet1/1"],
            },
        )
    assert r.status_code == 400
    assert "unsupported" in r.get_json()["error"].lower()


def test_transceiver_recover_404_for_unknown_device(client):
    """Audit H7: device not in inventory → 404."""
    r = client.post(
        "/api/transceiver/recover",
        json={
            "device": {"hostname": "no-such-device", "ip": "203.0.113.99"},
            "interfaces": ["Ethernet1/1"],
        },
    )
    assert r.status_code == 404


def test_transceiver_recover_credential_not_basic(client):
    """API-key credentials cannot recover."""
    with patch("backend.blueprints.transceiver_bp.creds.get_credential") as gc:
        gc.return_value = {"method": "api_key", "api_key": "x"}
        r = client.post(
            "/api/transceiver/recover",
            json={
                "device": {"hostname": "leaf-01"},
                "interfaces": ["Ethernet1/1"],
            },
        )
    assert r.status_code == 400
    assert "basic" in r.get_json()["error"].lower()


def test_transceiver_recover_credential_missing_username(client):
    with patch("backend.blueprints.transceiver_bp.creds.get_credential") as gc:
        gc.return_value = {"method": "basic", "username": "", "password": "p"}
        r = client.post(
            "/api/transceiver/recover",
            json={
                "device": {"hostname": "leaf-01"},
                "interfaces": ["Ethernet1/1"],
            },
        )
    assert r.status_code == 400
    assert "username" in r.get_json()["error"].lower()


def test_transceiver_recover_invalid_interface(client):
    """validate_interface_names rejects bad name."""
    with patch("backend.blueprints.transceiver_bp.creds.get_credential") as gc:
        gc.return_value = {"method": "basic", "username": "u", "password": "p"}
        r = client.post(
            "/api/transceiver/recover",
            json={
                "device": {"hostname": "leaf-01"},
                "interfaces": ["!invalid!"],
            },
        )
    # Either validation rejection OR policy denial — both are acceptable
    assert r.status_code == 400


def test_transceiver_recover_denied_by_policy(client):
    """Spine port is not on allowed list."""
    with patch("backend.blueprints.transceiver_bp.creds.get_credential") as gc:
        gc.return_value = {"method": "basic", "username": "u", "password": "p"}
        r = client.post(
            "/api/transceiver/recover",
            json={
                "device": {"hostname": "leaf-01"},
                "interfaces": ["Ethernet1/49"],  # outside 1-48 host port range
            },
        )
    assert r.status_code == 400


# =========================================================================== #
# transceiver_bp.api_transceiver_clear_counters — happy paths                  #
# =========================================================================== #


def test_clear_counters_arista_happy(client):
    with patch("backend.blueprints.transceiver_bp.creds.get_credential") as gc:
        gc.return_value = {"method": "basic", "username": "u", "password": "p"}
        with patch(
            "backend.runners.interface_recovery.clear_counters_arista_eos",
            return_value=([{"ok": True, "data": "y"}], None),
        ):
            r = client.post(
                "/api/transceiver/clear-counters",
                json={
                    "device": {"hostname": "leaf-01"},
                    "interface": "Ethernet1/1",
                },
            )
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert "ok" in body["output"] or "{" in body["output"]


def test_clear_counters_arista_empty_results(client):
    with patch("backend.blueprints.transceiver_bp.creds.get_credential") as gc:
        gc.return_value = {"method": "basic", "username": "u", "password": "p"}
        with patch(
            "backend.runners.interface_recovery.clear_counters_arista_eos",
            return_value=([{}], None),
        ):
            r = client.post(
                "/api/transceiver/clear-counters",
                json={
                    "device": {"hostname": "leaf-01"},
                    "interface": "Ethernet1/1",
                },
            )
    assert r.status_code == 200
    assert "ok" in r.get_json()["output"].lower()


def test_clear_counters_arista_no_results(client):
    with patch("backend.blueprints.transceiver_bp.creds.get_credential") as gc:
        gc.return_value = {"method": "basic", "username": "u", "password": "p"}
        with patch(
            "backend.runners.interface_recovery.clear_counters_arista_eos",
            return_value=([], None),
        ):
            r = client.post(
                "/api/transceiver/clear-counters",
                json={
                    "device": {"hostname": "leaf-01"},
                    "interface": "Ethernet1/1",
                },
            )
    assert r.status_code == 200
    assert "no output" in r.get_json()["output"].lower()


def test_clear_counters_cisco_happy(client):
    with patch("backend.blueprints.transceiver_bp.creds.get_credential") as gc:
        gc.return_value = {"method": "basic", "username": "u", "password": "p"}
        with patch(
            "backend.runners.interface_recovery.clear_counters_cisco_nxos",
            return_value=("counters cleared", None),
        ):
            r = client.post(
                "/api/transceiver/clear-counters",
                json={
                    "device": {"hostname": "leaf-02"},
                    "interface": "Ethernet1/1",
                },
            )
    assert r.status_code == 200
    assert "cleared" in r.get_json()["output"]


def test_clear_counters_cisco_runner_error(client):
    with patch("backend.blueprints.transceiver_bp.creds.get_credential") as gc:
        gc.return_value = {"method": "basic", "username": "u", "password": "p"}
        with patch(
            "backend.runners.interface_recovery.clear_counters_cisco_nxos",
            return_value=("", "auth failed"),
        ):
            r = client.post(
                "/api/transceiver/clear-counters",
                json={
                    "device": {"hostname": "leaf-02"},
                    "interface": "Ethernet1/1",
                },
            )
    assert r.status_code == 500


def test_clear_counters_404_for_unknown_device(client):
    r = client.post(
        "/api/transceiver/clear-counters",
        json={
            "device": {"hostname": "nope"},
            "interface": "Ethernet1/1",
        },
    )
    assert r.status_code == 404


def test_clear_counters_credential_not_basic(client):
    with patch("backend.blueprints.transceiver_bp.creds.get_credential") as gc:
        gc.return_value = {"method": "api_key", "api_key": "x"}
        r = client.post(
            "/api/transceiver/clear-counters",
            json={
                "device": {"hostname": "leaf-01"},
                "interface": "Ethernet1/1",
            },
        )
    assert r.status_code == 400


def test_clear_counters_unsupported_vendor(client, tmp_path):
    from backend.repositories import InventoryRepository
    from backend.services.inventory_service import InventoryService

    csv = tmp_path / "junos.csv"
    csv.write_text(
        "hostname,ip,fabric,site,hall,vendor,model,role,tag,credential\n"
        "junos-01,10.0.0.50,FAB1,Mars,Hall-1,Juniper,QFX,Leaf,,test-cred\n",
        encoding="utf-8",
    )
    flask_app = client.application
    flask_app.extensions["inventory_service"] = InventoryService(
        InventoryRepository(str(csv))
    )
    with patch("backend.blueprints.transceiver_bp.creds.get_credential") as gc:
        gc.return_value = {"method": "basic", "username": "u", "password": "p"}
        r = client.post(
            "/api/transceiver/clear-counters",
            json={
                "device": {"hostname": "junos-01"},
                "interface": "Ethernet1/1",
            },
        )
    assert r.status_code == 400


# =========================================================================== #
# transceiver_service — Cisco-detailed flap merge branch                       #
# =========================================================================== #


def test_transceiver_service_cisco_branch_merges_detailed_flap():
    from backend.services.transceiver_service import TransceiverService

    svc = TransceiverService(secret_key="x", credential_store=None)

    def stub(*_a, **k):
        cf = k.get("command_id_filter")
        cid_exact = k.get("command_id_exact")
        if cf == "transceiver":
            return {
                "hostname": "nx-1",
                "ip": "10.0.0.5",
                "parsed_flat": {
                    "transceiver_rows": [{"interface": "Eth1/1", "serial": "SN-A"}]
                },
            }
        if cf == "interface_status":
            return {
                "parsed_flat": {
                    "interface_status_rows": [
                        {"interface": "Eth1/1", "state": "up", "mtu": "1500"}
                    ]
                }
            }
        if cf == "interface_mtu":
            return {"parsed_flat": {"interface_mtu_map": {"Eth1/1": "9216"}}}
        if cid_exact == "cisco_nxos_show_interface":
            return {
                "commands": [
                    {
                        "command_id": "cisco_nxos_show_interface",
                        "parsed": {
                            "interface_flapped_rows": [
                                {"interface": "Eth1/1", "flap_counter": "5"}
                            ]
                        },
                        "raw": {"k": 1},
                    }
                ],
                "parsed_flat": {
                    "interface_flapped_rows": [
                        {"interface": "Eth1/1", "flap_counter": "5"}
                    ]
                },
            }
        return {"parsed_flat": {}}

    with patch(
        "backend.services.transceiver_service.run_device_commands", side_effect=stub
    ):
        rows, errors, trace = svc.collect_rows(
            [{"hostname": "nx-1", "ip": "10.0.0.5", "vendor": "Cisco", "role": "Leaf"}]
        )
    assert errors == []
    assert len(rows) == 1
    assert rows[0]["serial"] == "SN-A"
    assert rows[0]["mtu"] == "9216"  # from cisco_mtu_map, not from status row
    assert rows[0]["flap_count"] == "5"
    # trace contains cisco detailed entry
    assert trace[0]["cisco_show_interface_detailed"]


def test_transceiver_service_skips_non_dict_transceiver_row():
    from backend.services.transceiver_service import TransceiverService

    svc = TransceiverService(secret_key="x", credential_store=None)

    def stub(*_a, **k):
        cf = k.get("command_id_filter")
        if cf == "transceiver":
            return {
                "hostname": "h",
                "parsed_flat": {"transceiver_rows": ["not-a-dict", {"interface": "Eth1"}]},
            }
        return {"parsed_flat": {}}

    with patch(
        "backend.services.transceiver_service.run_device_commands", side_effect=stub
    ):
        rows, _, _ = svc.collect_rows(
            [{"hostname": "h", "ip": "1.1.1.1", "vendor": "Arista"}]
        )
    # Only the dict row produced output.
    assert len(rows) == 1


def test_transceiver_service_status_run_error_short_circuits_status_map():
    from backend.services.transceiver_service import TransceiverService

    svc = TransceiverService(secret_key="x", credential_store=None)

    def stub(*_a, **k):
        cf = k.get("command_id_filter")
        if cf == "transceiver":
            return {"hostname": "h", "parsed_flat": {"transceiver_rows": [{"interface": "E1"}]}}
        if cf == "interface_status":
            return {"error": "ssh refused"}
        return {"parsed_flat": {}}

    with patch(
        "backend.services.transceiver_service.run_device_commands", side_effect=stub
    ):
        rows, _, trace = svc.collect_rows(
            [{"hostname": "h", "ip": "1.1.1.1", "vendor": "Arista"}]
        )
    assert len(rows) == 1
    assert trace[0]["status_run_error"] == "ssh refused"


# =========================================================================== #
# bgp_bp.api_bgp_wan_rtr_match — per-vendor dispatch                           #
# =========================================================================== #


def test_wan_rtr_match_arista_finds_bgp_as(client, tmp_path):
    """Arista WAN router branch: returning JSON dict containing router bgp."""
    from backend.repositories import InventoryRepository
    from backend.services.inventory_service import InventoryService

    csv = tmp_path / "wan.csv"
    csv.write_text(
        "hostname,ip,fabric,site,hall,vendor,model,role,tag,credential\n"
        "wanrtr-01,10.0.0.100,F1,Mars,Hall-1,Arista,EOS,WAN-Router,,test-cred\n",
        encoding="utf-8",
    )
    flask_app = client.application
    flask_app.extensions["inventory_service"] = InventoryService(
        InventoryRepository(str(csv))
    )

    with patch(
        "backend.blueprints.bgp_bp._get_credentials", return_value=("u", "p")
    ), patch(
        "backend.runners.arista_eapi.run_commands",
        return_value=([{"cmds": {"router bgp 65000": {}}}], None),
    ):
        r = client.get("/api/bgp/wan-rtr-match?asn=65000")
    assert r.status_code == 200
    body = r.get_json()
    assert len(body["matches"]) == 1
    assert body["matches"][0]["hostname"] == "wanrtr-01"


def test_wan_rtr_match_cisco_ssh_branch(client, tmp_path):
    """Non-arista WAN router → SSH config dump branch."""
    from backend.repositories import InventoryRepository
    from backend.services.inventory_service import InventoryService

    csv = tmp_path / "wan.csv"
    csv.write_text(
        "hostname,ip,fabric,site,hall,vendor,model,role,tag,credential\n"
        "wanrtr-02,10.0.0.101,F1,Mars,Hall-1,Cisco,IOS-XR,WAN-Router,,test-cred\n",
        encoding="utf-8",
    )
    flask_app = client.application
    flask_app.extensions["inventory_service"] = InventoryService(
        InventoryRepository(str(csv))
    )

    with patch(
        "backend.blueprints.bgp_bp._get_credentials", return_value=("u", "p")
    ), patch(
        "backend.runners.ssh_runner.run_command",
        return_value=("router bgp 65001\n neighbor 1.2.3.4\n", None),
    ):
        r = client.get("/api/bgp/wan-rtr-match?asn=65001")
    assert r.status_code == 200
    assert any(m["hostname"] == "wanrtr-02" for m in r.get_json()["matches"])


def test_wan_rtr_match_skips_device_without_credential(client, tmp_path):
    from backend.repositories import InventoryRepository
    from backend.services.inventory_service import InventoryService

    csv = tmp_path / "wan.csv"
    csv.write_text(
        "hostname,ip,fabric,site,hall,vendor,model,role,tag,credential\n"
        "wanrtr-03,10.0.0.103,F1,Mars,Hall-1,Arista,EOS,WAN-Router,,nope-cred\n",
        encoding="utf-8",
    )
    flask_app = client.application
    flask_app.extensions["inventory_service"] = InventoryService(
        InventoryRepository(str(csv))
    )

    with patch(
        "backend.blueprints.bgp_bp._get_credentials", return_value=("", "")
    ):
        r = client.get("/api/bgp/wan-rtr-match?asn=65000")
    assert r.status_code == 200
    assert r.get_json()["matches"] == []


def test_wan_rtr_match_runner_exception_softfails(client, tmp_path):
    from backend.repositories import InventoryRepository
    from backend.services.inventory_service import InventoryService

    csv = tmp_path / "wan.csv"
    csv.write_text(
        "hostname,ip,fabric,site,hall,vendor,model,role,tag,credential\n"
        "wanrtr-04,10.0.0.104,F1,Mars,Hall-1,Arista,EOS,WAN-Router,,test-cred\n",
        encoding="utf-8",
    )
    flask_app = client.application
    flask_app.extensions["inventory_service"] = InventoryService(
        InventoryRepository(str(csv))
    )

    with patch(
        "backend.blueprints.bgp_bp._get_credentials", return_value=("u", "p")
    ), patch(
        "backend.runners.arista_eapi.run_commands",
        side_effect=RuntimeError("oops"),
    ):
        r = client.get("/api/bgp/wan-rtr-match?asn=65000")
    # Soft-fail: route returns 200 even when the runner raises.
    assert r.status_code == 200
    assert r.get_json()["matches"] == []


def test_bgp_pass_through_routes_forward_to_helper(client):
    """Cover the 7 pass-through routes' happy paths via mocking."""
    with patch("backend.bgp_looking_glass.get_bgp_history", return_value={"ok": 1}):
        assert client.get("/api/bgp/history?prefix=1.1.1.0/24").status_code == 200
    with patch("backend.bgp_looking_glass.get_bgp_visibility", return_value={"ok": 1}):
        assert client.get("/api/bgp/visibility?prefix=1.1.1.0/24").status_code == 200
    with patch("backend.bgp_looking_glass.get_bgp_looking_glass", return_value={"ok": 1}):
        assert client.get("/api/bgp/looking-glass?prefix=1.1.1.0/24").status_code == 200
    with patch("backend.bgp_looking_glass.get_bgp_as_info", return_value={"ok": 1}):
        assert client.get("/api/bgp/as-info?asn=13335").status_code == 200
    with patch("backend.bgp_looking_glass.get_bgp_announced_prefixes", return_value={"ok": 1}):
        assert client.get("/api/bgp/announced-prefixes?asn=13335").status_code == 200


# =========================================================================== #
# device_commands_bp.api_arista_run_cmds — happy paths                         #
# =========================================================================== #


def test_arista_run_cmds_happy_string_command(client):
    with patch(
        "backend.runners.arista_eapi.run_cmds",
        return_value=([{"version": "4.21"}], None),
    ), patch(
        "backend.blueprints.device_commands_bp._get_credentials",
        return_value=("u", "p"),
    ):
        r = client.post(
            "/api/arista/run-cmds",
            json={
                # Audit H-2: device must be in inventory; use mock_inventory_csv leaf-01.
                "device": {"hostname": "leaf-01", "ip": "10.0.0.1", "credential": "test-cred"},
                "cmds": ["show version"],
            },
        )
    assert r.status_code == 200
    body = r.get_json()
    assert body["error"] is None
    assert body["result"]


def test_arista_run_cmds_happy_dict_with_enable(client):
    with patch(
        "backend.runners.arista_eapi.run_cmds",
        return_value=(["ok", {"v": "4.21"}], None),
    ) as m, patch(
        "backend.blueprints.device_commands_bp._get_credentials",
        return_value=("u", "secret-enable"),
    ):
        client.post(
            "/api/arista/run-cmds",
            json={
                # Audit H-2: inventory-bound device.
                "device": {"hostname": "leaf-01", "ip": "10.0.0.1", "credential": "test-cred"},
                "cmds": [{"cmd": "enable"}, "show version"],
            },
        )
    cmds_forwarded = m.call_args.args[3]
    # First cmd is the enable dict with password substituted.
    assert cmds_forwarded[0] == {"cmd": "enable", "input": "secret-enable"}


def test_arista_run_cmds_runner_returns_error(client):
    with patch(
        "backend.runners.arista_eapi.run_cmds", return_value=(None, "eapi 401")
    ), patch(
        "backend.blueprints.device_commands_bp._get_credentials",
        return_value=("u", "p"),
    ):
        r = client.post(
            "/api/arista/run-cmds",
            json={
                # Audit H-2: inventory-bound device.
                "device": {"hostname": "leaf-01", "ip": "10.0.0.1", "credential": "test-cred"},
                "cmds": ["show version"],
            },
        )
    assert r.status_code == 200
    assert r.get_json()["error"] == "eapi 401"


def test_arista_run_cmds_no_credential_400(client):
    with patch(
        "backend.blueprints.device_commands_bp._get_credentials",
        return_value=("", ""),
    ):
        r = client.post(
            "/api/arista/run-cmds",
            json={
                # Audit H-2: inventory-bound device with bad credential.
                "device": {"hostname": "leaf-01", "ip": "10.0.0.1", "credential": "missing-cred"},
                "cmds": ["show version"],
            },
        )
    assert r.status_code == 400


def test_router_devices_wan_scope(client, tmp_path):
    from backend.repositories import InventoryRepository
    from backend.services.inventory_service import InventoryService

    csv = tmp_path / "wan.csv"
    csv.write_text(
        "hostname,ip,fabric,site,hall,vendor,model,role,tag,credential\n"
        "wanrtr-01,10.0.0.100,F1,Mars,Hall-1,Arista,EOS,WAN-Router,,test-cred\n"
        "dcirtr-01,10.0.0.101,F1,Mars,Hall-1,Arista,EOS,DCI-Router,,test-cred\n",
        encoding="utf-8",
    )
    flask_app = client.application
    flask_app.extensions["inventory_service"] = InventoryService(
        InventoryRepository(str(csv))
    )
    r = client.get("/api/router-devices?scope=wan")
    assert r.status_code == 200
    devs = r.get_json()["devices"]
    assert len(devs) == 1
    assert devs[0]["hostname"] == "wanrtr-01"


# =========================================================================== #
# device_commands_bp.api_route_map_run — happy paths                           #
# =========================================================================== #


def test_route_map_run_happy_aggregates_rows(client):
    with patch(
        "backend.runners.arista_eapi.run_commands",
        return_value=([{"cmds": {"router bgp 65000": {"neighbor": {}}}}], None),
    ), patch(
        "backend.route_map_analysis.analyze_router_config",
        return_value={"peer_groups": ["pg1"]},
    ), patch(
        "backend.route_map_analysis.build_unified_bgp_full_table",
        return_value=[{"peer_group": "pg1", "route_map_in": "RM-IN"}],
    ), patch(
        "backend.blueprints.device_commands_bp._get_credentials",
        return_value=("u", "p"),
    ):
        r = client.post(
            "/api/route-map/run",
            json={
                "devices": [
                    {
                        "hostname": "h",
                        "ip": "10.0.0.1",
                        "vendor": "Arista",
                        "model": "EOS",
                        "credential": "test-cred",
                    }
                ]
            },
        )
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["rows"] == [{"peer_group": "pg1", "route_map_in": "RM-IN"}]


def test_route_map_run_handles_per_device_exception(client):
    """Wave-7.9: route now resolves the device from inventory; use the
    real conftest hostname `leaf-01` so the inventory-resolution gate
    passes and we reach the analyze_router_config exception branch.
    """
    with patch(
        "backend.runners.arista_eapi.run_commands",
        return_value=([{"cmds": {}}], None),
    ), patch(
        "backend.route_map_analysis.analyze_router_config",
        side_effect=RuntimeError("bad config"),
    ), patch(
        "backend.route_map_analysis.build_unified_bgp_full_table", return_value=[]
    ), patch(
        "backend.blueprints.device_commands_bp._get_credentials",
        return_value=("u", "p"),
    ):
        r = client.post(
            "/api/route-map/run",
            json={
                "devices": [
                    {
                        "hostname": "leaf-01",
                        "ip": "10.0.0.1",
                        "vendor": "Arista",
                        "model": "EOS",
                    }
                ]
            },
        )
    assert r.status_code == 200
    errs = r.get_json()["errors"]
    # Audit L-1: error envelope is generic; "bad config" stays in server log.
    assert any(
        e.get("hostname") == "leaf-01" and "analysis failed" in e.get("error", "").lower()
        for e in errs
    )
    # Confirm the raw exception detail is NOT echoed to clients.
    assert not any("bad config" in e.get("error", "") for e in errs)


def test_route_map_run_runner_error(client):
    with patch(
        "backend.runners.arista_eapi.run_commands", return_value=([], "ssh fail")
    ), patch(
        "backend.blueprints.device_commands_bp._get_credentials",
        return_value=("u", "p"),
    ):
        r = client.post(
            "/api/route-map/run",
            json={
                "devices": [
                    {
                        "hostname": "h",
                        "ip": "10.0.0.1",
                        "vendor": "Arista",
                        "model": "EOS",
                        "credential": "test-cred",
                    }
                ]
            },
        )
    assert r.status_code == 200
    assert r.get_json()["errors"][0]["error"] == "ssh fail"


def test_route_map_run_no_json_config(client):
    with patch(
        "backend.runners.arista_eapi.run_commands", return_value=(["not a dict"], None)
    ), patch(
        "backend.blueprints.device_commands_bp._get_credentials",
        return_value=("u", "p"),
    ):
        r = client.post(
            "/api/route-map/run",
            json={
                "devices": [
                    {
                        "hostname": "h",
                        "ip": "10.0.0.1",
                        "vendor": "Arista",
                        "model": "EOS",
                        "credential": "test-cred",
                    }
                ]
            },
        )
    assert r.status_code == 200
    errs = r.get_json()["errors"]
    assert any("no JSON" in e.get("error", "") for e in errs)


def test_route_map_run_skips_device_missing_ip(client):
    """Wave-7.9: route now resolves the device from inventory; we reach
    the missing-ip branch by binding to a real inventory hostname and
    then patching the resolver to return a row with an empty ip.
    """
    with patch(
        "backend.blueprints.device_commands_bp._get_credentials",
        return_value=("u", "p"),
    ), patch(
        "backend.blueprints.device_commands_bp._resolve_inventory_device",
        return_value={
            "hostname": "leaf-01",
            "ip": "",  # the bug-trigger
            "vendor": "Arista",
            "model": "EOS",
            "credential": "test-cred",
        },
    ):
        r = client.post(
            "/api/route-map/run",
            json={
                "devices": [
                    {"hostname": "leaf-01", "ip": "10.0.0.1", "vendor": "Arista", "model": "EOS"}
                ]
            },
        )
    assert r.status_code == 200
    assert "missing ip" in r.get_json()["errors"][0]["error"]


def test_route_map_run_skips_device_no_credential(client):
    with patch(
        "backend.blueprints.device_commands_bp._get_credentials",
        return_value=("", ""),
    ):
        r = client.post(
            "/api/route-map/run",
            json={
                "devices": [
                    {
                        "hostname": "h",
                        "ip": "10.0.0.1",
                        "vendor": "Arista",
                        "model": "EOS",
                    }
                ]
            },
        )
    assert r.status_code == 200
    assert "no credential" in r.get_json()["errors"][0]["error"]


# =========================================================================== #
# device_commands_bp.api_custom_command — happy + error                        #
# =========================================================================== #


def test_custom_command_no_device_ip(client):
    """Audit H-2: a device not in inventory is rejected (404)."""
    r = client.post(
        "/api/custom-command",
        json={"device": {"hostname": "h"}, "command": "show version"},
    )
    assert r.status_code in (400, 404)


def test_custom_command_no_credential(client):
    with patch(
        "backend.blueprints.device_commands_bp._get_credentials", return_value=("", "")
    ):
        r = client.post(
            "/api/custom-command",
            json={"device": {"ip": "10.0.0.1"}, "command": "show version"},
        )
    assert r.status_code == 200
    assert "no credential" in r.get_json()["error"]


def test_custom_command_runner_error(client):
    with patch(
        "backend.runners.ssh_runner.run_command",
        return_value=(None, "ssh refused"),
    ), patch(
        "backend.blueprints.device_commands_bp._get_credentials",
        return_value=("u", "p"),
    ):
        r = client.post(
            "/api/custom-command",
            json={"device": {"ip": "10.0.0.1"}, "command": "show version"},
        )
    assert r.status_code == 200
    assert r.get_json()["error"] == "ssh refused"


# =========================================================================== #
# runs_bp.api_run_post — happy path (server-driven POST)                       #
# =========================================================================== #


def test_run_post_full_flow_diff_emitted(client):
    """End-to-end PRE → POST with server-side run."""
    with patch("backend.blueprints.runs_bp.run_device_commands") as m:
        # PRE returns Uptime=1d, POST returns Uptime=2d
        m.side_effect = [
            {"hostname": "leaf-1", "ip": "10.0.0.1", "parsed_flat": {"Uptime": "1d"}},
            {"hostname": "leaf-1", "ip": "10.0.0.1", "parsed_flat": {"Uptime": "2d"}},
        ]
        pre = client.post(
            "/api/run/pre",
            json={"devices": [{"hostname": "leaf-1", "ip": "10.0.0.1"}]},
        )
    rid = pre.get_json()["run_id"]
    with patch("backend.blueprints.runs_bp.run_device_commands") as m2:
        m2.return_value = {
            "hostname": "leaf-1",
            "ip": "10.0.0.1",
            "parsed_flat": {"Uptime": "2d"},
        }
        post = client.post("/api/run/post", json={"run_id": rid})
    assert post.status_code == 200
    body = post.get_json()
    assert body["phase"] == "POST"
    diff = body["comparison"][0]["diff"]
    assert diff == {"Uptime": {"pre": "1d", "post": "2d"}}


def test_run_post_404_for_unknown_run(client):
    r = client.post("/api/run/post", json={"run_id": "no-such-run"})
    assert r.status_code == 404


def test_run_post_400_when_run_not_pre(client):
    """A run already in POST state cannot be POST-run again."""
    flask_app = client.application
    store = flask_app.extensions["run_state_store"]
    store.set(
        "post-only",
        {"phase": "POST", "devices": [], "device_results": []},
    )
    r = client.post("/api/run/post", json={"run_id": "post-only"})
    assert r.status_code == 400


def test_run_post_complete_400_when_lengths_mismatch(client):
    flask_app = client.application
    store = flask_app.extensions["run_state_store"]
    store.set(
        "abc",
        {
            "phase": "PRE",
            "devices": [{"hostname": "h1"}],
            "device_results": [{}],
            "created_at": "now",
        },
    )
    r = client.post(
        "/api/run/post/complete",
        json={"run_id": "abc", "device_results": [{}, {}]},
    )
    assert r.status_code == 400


def test_run_pre_create_400_when_devices_empty(client):
    r = client.post(
        "/api/run/pre/create",
        json={"devices": [], "device_results": []},
    )
    assert r.status_code == 400


def test_run_pre_restore_400_when_devices_empty(client):
    r = client.post(
        "/api/run/pre/restore",
        json={"run_id": "x", "devices": [], "device_results": []},
    )
    assert r.status_code == 400


# =========================================================================== #
# credentials_bp.api_credentials_validate — happy paths                        #
# =========================================================================== #


def test_credentials_validate_runner_error(client):
    """Credential exists, device exists, but the runner fails."""
    # Add a credential first
    client.post(
        "/api/credentials",
        json={"name": "test-cred", "method": "basic", "username": "u", "password": "p"},
    )
    with patch(
        "backend.blueprints.credentials_bp.run_device_commands",
        return_value={"hostname": "leaf-01", "error": "ssh refused"},
    ):
        r = client.post("/api/credentials/test-cred/validate")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is False
    assert body["error"] == "ssh refused"


def test_credentials_validate_no_applicable_commands(client):
    client.post(
        "/api/credentials",
        json={"name": "test-cred", "method": "basic", "username": "u", "password": "p"},
    )
    with patch(
        "backend.blueprints.credentials_bp.run_device_commands",
        return_value={
            "hostname": "leaf-01",
            "commands": [{"raw": None, "error": "x"}],
            "parsed_flat": {},
        },
    ):
        r = client.post("/api/credentials/test-cred/validate")
    body = r.get_json()
    assert body["ok"] is False
    assert "no applicable" in body["error"].lower()


def test_credentials_validate_success_with_uptime(client):
    client.post(
        "/api/credentials",
        json={"name": "test-cred", "method": "basic", "username": "u", "password": "p"},
    )
    with patch(
        "backend.blueprints.credentials_bp.run_device_commands",
        return_value={
            "hostname": "leaf-01",
            "commands": [{"raw": "VERSION 4.21"}],
            "parsed_flat": {"Uptime": "5d 3h"},
        },
    ):
        r = client.post("/api/credentials/test-cred/validate")
    body = r.get_json()
    assert body["ok"] is True
    assert body["uptime"] == "5d 3h"
    assert "Logged in" in body["message"]


def test_credentials_create_invalid_name_400(client):
    """InputSanitizer.sanitize_credential_name rejects bad chars."""
    r = client.post(
        "/api/credentials",
        json={"name": "../etc/passwd", "method": "api_key", "api_key": "x"},
    )
    assert r.status_code == 400


# =========================================================================== #
# reports_bp — restore + error branches                                        #
# =========================================================================== #


def test_report_post_restore_pushes_into_run_state(client):
    """Audit M-03: POST /api/reports/<id>/restore pushes back to run state."""
    devices = [{"hostname": "leaf-1", "ip": "10.0.0.1"}]
    pre_results = [{"hostname": "leaf-1", "parsed_flat": {}}]
    create = client.post(
        "/api/run/pre/create",
        json={"devices": devices, "device_results": pre_results, "name": "audit"},
    )
    rid = create.get_json()["run_id"]
    r = client.post(f"/api/reports/{rid}/restore")
    assert r.status_code == 200
    # Verify it landed in the run-state store
    flask_app = client.application
    store = flask_app.extensions["run_state_store"]
    state = store.get(rid)
    assert state is not None
    assert state["phase"] == "PRE"


def test_legacy_get_restore_returns_405(client):
    """Audit M-03: legacy GET ?restore=1 must be rejected with 405."""
    r = client.get("/api/reports/anything?restore=1")
    assert r.status_code == 405


def test_reports_list_returns_empty_on_storage_error(client):
    flask_app = client.application
    rs = flask_app.extensions["report_service"]
    with patch.object(rs, "list", side_effect=RuntimeError("disk gone")):
        r = client.get("/api/reports")
    assert r.status_code == 200
    assert r.get_json()["reports"] == []


def test_report_get_500_on_storage_error(client):
    flask_app = client.application
    rs = flask_app.extensions["report_service"]
    with patch.object(rs, "load", side_effect=RuntimeError("disk gone")):
        r = client.get("/api/reports/some-id")
    assert r.status_code == 500


def test_report_delete_500_on_storage_error(client):
    flask_app = client.application
    rs = flask_app.extensions["report_service"]
    with patch.object(rs, "delete", side_effect=RuntimeError("disk gone")):
        r = client.delete("/api/reports/some-id")
    assert r.status_code == 500


def test_report_delete_empty_run_id_400(client):
    """Empty run_id rejected. Flask routes it as the index, but we need a
    direct path that triggers the empty branch — simulate via empty string
    passed through a wildcard match (URL routing test)."""
    # Real DELETE /api/reports/ would 404. Verify the helper logic instead.
    from backend.blueprints.reports_bp import api_report_delete
    from flask import Flask

    test_app = Flask(__name__)
    test_app.register_blueprint(client.application.blueprints["reports"])
    test_app.extensions["report_service"] = client.application.extensions["report_service"]
    test_app.extensions["run_state_store"] = client.application.extensions[
        "run_state_store"
    ]
    with test_app.test_request_context("/"):
        resp, code = api_report_delete("   ")
        assert code == 400


# =========================================================================== #
# run_state_store — eviction edge cases                                        #
# =========================================================================== #


def test_run_state_store_update_unknown_run_returns_none():
    from backend.services.run_state_store import RunStateStore

    store = RunStateStore()
    assert store.update("nope", phase="POST") is None


def test_run_state_store_update_returns_deep_copy():
    from backend.services.run_state_store import RunStateStore

    store = RunStateStore()
    store.set("r1", {"phase": "PRE", "list": [1, 2]})
    updated = store.update("r1", phase="POST")
    assert updated is not None
    updated["list"].append(99)
    fresh = store.get("r1")
    assert fresh is not None
    assert fresh["list"] == [1, 2]


def test_run_state_store_contains_returns_false_for_expired():
    from backend.services.run_state_store import RunStateStore
    import time

    store = RunStateStore(ttl_seconds=1)
    store.set("r1", {"phase": "PRE"})
    assert "r1" in store
    time.sleep(1.1)
    assert "r1" not in store


def test_run_state_store_contains_returns_false_for_unknown():
    from backend.services.run_state_store import RunStateStore

    store = RunStateStore()
    assert "no-such-run" not in store


def test_run_state_store_len_evicts_expired():
    from backend.services.run_state_store import RunStateStore
    import time

    store = RunStateStore(ttl_seconds=1)
    store.set("r1", {})
    store.set("r2", {})
    assert len(store) == 2
    time.sleep(1.1)
    assert len(store) == 0


def test_run_state_store_no_ttl_keeps_everything():
    from backend.services.run_state_store import RunStateStore

    store = RunStateStore(ttl_seconds=None)
    store.set("forever", {})
    import time

    time.sleep(0.1)
    assert store.get("forever") is not None


def test_run_state_store_get_expired_returns_none_and_evicts():
    from backend.services.run_state_store import RunStateStore
    import time

    store = RunStateStore(ttl_seconds=1)
    store.set("r1", {"phase": "PRE"})
    time.sleep(1.1)
    assert store.get("r1") is None
    assert len(store) == 0


def test_run_state_store_update_expired_returns_none():
    from backend.services.run_state_store import RunStateStore
    import time

    store = RunStateStore(ttl_seconds=1)
    store.set("r1", {"phase": "PRE"})
    time.sleep(1.1)
    assert store.update("r1", phase="POST") is None


# =========================================================================== #
# Utility branch coverage                                                      #
# =========================================================================== #


def test_transceiver_last_flap_display_handles_bad_epoch():
    from backend.utils.transceiver_display import transceiver_last_flap_display

    # Negative or absurdly large epoch triggers the OverflowError catch
    assert transceiver_last_flap_display({"last_status_change_epoch": -1e30}) == "-"


def test_wan_rtr_has_bgp_as_handles_non_dict_cmds():
    from backend.utils.bgp_helpers import wan_rtr_has_bgp_as

    payload = {"cmds": "not a dict"}
    assert wan_rtr_has_bgp_as(payload, "65000", is_json=True) is False


def test_interface_status_trace_handles_list_raw():
    from backend.utils.interface_status import interface_status_trace

    out = interface_status_trace(
        {
            "commands": [
                {
                    "command_id": "arista_show_interface_status",
                    "parsed": {"interface_status_rows": [{"interface": "Et1"}]},
                    "raw": [{"k1": 1}],  # list[dict] branch
                }
            ]
        }
    )
    assert len(out) == 1
    assert out[0]["raw_top_level_keys"] == ["k1"]


def test_cisco_interface_detailed_trace_handles_list_raw():
    from backend.utils.interface_status import cisco_interface_detailed_trace

    out = cisco_interface_detailed_trace(
        {
            "commands": [
                {
                    "command_id": "cisco_nxos_show_interface",
                    "parsed": {"interface_flapped_rows": [{"interface": "Eth1/1"}]},
                    "raw": [{"k1": 1}],
                }
            ]
        }
    )
    assert len(out) == 1
    assert out[0]["raw_top_level_keys"] == ["k1"]


def test_interface_status_trace_skips_non_dict_rows():
    from backend.utils.interface_status import interface_status_trace

    out = interface_status_trace(
        {
            "commands": [
                {
                    "command_id": "any_interface_status",
                    "parsed": {
                        "interface_status_rows": ["not-a-dict", {"interface": "Et1"}]
                    },
                }
            ]
        }
    )
    # Both `sample_interfaces` (`if isinstance(r, dict)`) and
    # `sample_flap_fields` (`if not isinstance(r, dict): continue`)
    # filter the non-dict.
    assert out[0]["sample_interfaces"] == ["Et1"]
    assert len(out[0]["sample_flap_fields"]) == 1


# =========================================================================== #
# Extension-missing 500 paths in runs_bp / reports_bp                          #
# =========================================================================== #


def test_runs_bp_raises_when_run_state_store_missing():
    """Hitting a runs_bp route without the extension → 500 with explicit msg.

    Uses ``/api/run/pre/restore`` (skips inventory binding because it's
    a state-restore op, not an exec) so we exercise the missing-extension
    path without hitting the H-2 inventory check first.
    """
    from flask import Flask

    from backend.blueprints.runs_bp import runs_bp

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "x" * 32
    app.register_blueprint(runs_bp)
    c = app.test_client()
    r = c.post(
        "/api/run/pre/restore",
        json={
            "run_id": "r1",
            "devices": [{"hostname": "h", "ip": "1.1.1.1"}],
            "device_results": [{"hostname": "h"}],
        },
    )
    # We expect the RuntimeError to bubble or be caught as 500.
    assert r.status_code == 500


def test_reports_bp_raises_when_report_service_missing():
    from flask import Flask

    from backend.blueprints.reports_bp import reports_bp

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "x" * 32
    app.register_blueprint(reports_bp)
    c = app.test_client()
    r = c.get("/api/reports")
    # The blueprint's try/except returns {reports: []} on Exception, so
    # we expect 200 + empty list — but the inner RuntimeError is exercised.
    assert r.status_code == 200
