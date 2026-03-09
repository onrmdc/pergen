"""
Flask app for network device panel.
Run from repo root: FLASK_APP=backend.app flask run
"""
import gzip
import json
import os
import sys
import uuid
import subprocess
import platform

# Ensure project root is on path when running as flask run
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify, request, send_from_directory

from backend.config import settings
from backend.inventory.loader import (
    load_inventory,
    save_inventory,
    get_fabrics,
    get_sites,
    get_halls,
    get_roles,
    get_devices,
    get_devices_by_tag,
    INVENTORY_HEADER,
)
from backend import find_leaf as find_leaf_module
from backend import nat_lookup as nat_lookup_module
from backend import route_map_analysis as route_map_analysis_module
from backend import bgp_looking_glass as bgp_lg
from backend import credential_store as creds
from backend.config import commands_loader as cmd_loader
from backend.runners.runner import run_device_commands, _get_credentials

_static = os.path.join(os.path.dirname(__file__), "static")
app = Flask(__name__, static_folder=_static if os.path.isdir(_static) else None)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-in-prod")

# Init credential DB on startup (once)
creds.init_db(app.config["SECRET_KEY"])

# Pre/Post run state: run_id -> { phase, devices, device_results, created_at }
_run_state = {}

# Saved reports: persisted to disk (gzip), index for list
def _reports_dir():
    d = os.path.join(app.instance_path, "reports")
    os.makedirs(d, exist_ok=True)
    return d


def _reports_index_path():
    return os.path.join(_reports_dir(), "index.json")


def _report_path(run_id):
    safe = (run_id or "").replace("/", "_").replace("\\", "_") or "default"
    return os.path.join(_reports_dir(), safe + ".json.gz")


def _load_reports_index():
    path = _reports_index_path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_reports_index(entries):
    path = _reports_index_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries[:200], f, ensure_ascii=False)  # cap 200


def _persist_report(run_id, name, created_at, devices, device_results, post_created_at=None, post_device_results=None, comparison=None):
    path = _report_path(run_id)
    payload = {
        "run_id": run_id,
        "name": name or "pre_report",
        "created_at": created_at,
        "devices": devices,
        "device_results": device_results,
        "post_created_at": post_created_at,
        "post_device_results": post_device_results,
        "comparison": comparison,
    }
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    entries = _load_reports_index()
    by_id = {e.get("run_id"): i for i, e in enumerate(entries)}
    meta = {"run_id": run_id, "name": name or "pre_report", "created_at": created_at, "post_created_at": post_created_at}
    if run_id in by_id:
        entries[by_id[run_id]] = meta
    else:
        entries.insert(0, meta)
    _save_reports_index(entries)


def _load_report(run_id):
    path = _report_path(run_id)
    if not os.path.isfile(path):
        return None
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _delete_report(run_id):
    path = _report_path(run_id)
    if os.path.isfile(path):
        try:
            os.remove(path)
        except Exception:
            pass
    entries = _load_reports_index()
    entries = [e for e in entries if (e.get("run_id") or "") != (run_id or "")]
    _save_reports_index(entries)


def _inventory_path():
    path = settings.INVENTORY_PATH
    if not os.path.isfile(path) and os.path.isfile(settings.EXAMPLE_INVENTORY_PATH):
        return settings.EXAMPLE_INVENTORY_PATH
    return path


# ---------- Inventory hierarchy ----------
@app.route("/api/fabrics", methods=["GET"])
def api_fabrics():
    devs = load_inventory(_inventory_path())
    return jsonify({"fabrics": get_fabrics(devs)})


@app.route("/api/sites", methods=["GET"])
def api_sites():
    fabric = (request.args.get("fabric") or "").strip()
    if not fabric:
        return jsonify({"sites": []})
    devs = load_inventory(_inventory_path())
    return jsonify({"sites": get_sites(fabric, devs)})


@app.route("/api/halls", methods=["GET"])
def api_halls():
    fabric = (request.args.get("fabric") or "").strip()
    site = (request.args.get("site") or "").strip()
    if not fabric:
        return jsonify({"halls": []})
    devs = load_inventory(_inventory_path())
    return jsonify({"halls": get_halls(fabric, site, devs)})


@app.route("/api/devices-by-tag", methods=["GET"])
def api_devices_by_tag():
    """Return devices with the given tag. Optional fabric= & site= filter. Returns { devices: [ { hostname, ip }, ... ] }."""
    tag = (request.args.get("tag") or "").strip()
    if not tag:
        return jsonify({"devices": []})
    fabric = (request.args.get("fabric") or "").strip()
    site = (request.args.get("site") or "").strip()
    devs = load_inventory(_inventory_path())
    matched = get_devices_by_tag(tag, devs)
    if fabric:
        matched = [d for d in matched if (d.get("fabric") or "").strip() == fabric]
    if site:
        matched = [d for d in matched if (d.get("site") or "").strip() == site]
    devices = [{"hostname": (d.get("hostname") or "").strip(), "ip": (d.get("ip") or "").strip()} for d in matched]
    return jsonify({"devices": devices})


@app.route("/api/roles", methods=["GET"])
def api_roles():
    fabric = (request.args.get("fabric") or "").strip()
    site = (request.args.get("site") or "").strip()
    hall = (request.args.get("hall") or "").strip() or None
    if not fabric:
        return jsonify({"roles": []})
    devs = load_inventory(_inventory_path())
    return jsonify({"roles": get_roles(fabric, site, hall, devs)})


@app.route("/api/devices", methods=["GET"])
def api_devices():
    fabric = (request.args.get("fabric") or "").strip()
    site = (request.args.get("site") or "").strip()
    role = (request.args.get("role") or "").strip() or None
    hall = (request.args.get("hall") or "").strip() or None
    if not fabric:
        return jsonify({"devices": []})
    devs = load_inventory(_inventory_path())
    devices = get_devices(fabric, site, role=role, hall=hall, devices=devs)
    return jsonify({"devices": devices})


@app.route("/api/devices-arista", methods=["GET"])
def api_devices_arista():
    """Return only Arista EOS devices. Same query params as /api/devices (fabric, site, hall, role)."""
    fabric = (request.args.get("fabric") or "").strip()
    site = (request.args.get("site") or "").strip()
    role = (request.args.get("role") or "").strip() or None
    hall = (request.args.get("hall") or "").strip() or None
    if not fabric:
        return jsonify({"devices": []})
    devs = load_inventory(_inventory_path())
    devices = get_devices(fabric, site, role=role, hall=hall, devices=devs)
    arista = [
        d for d in devices
        if (d.get("vendor") or "").strip().lower() == "arista"
        or (d.get("model") or "").strip().lower() == "eos"
    ]
    return jsonify({"devices": arista})


@app.route("/api/arista/run-cmds", methods=["POST"])
def api_arista_run_cmds():
    """
    Run arbitrary eAPI runCmds on one Arista device. Body: { "device": { hostname, ip, credential, ... }, "cmds": [ str | { "cmd": "enable", "input": "..." }, ... ] }.
    Enable password is substituted from credential; other cmds are sent as-is. Returns { "result": [...], "error": null } or { "result": null, "error": "..." }.
    """
    data = request.get_json() or {}
    device = data.get("device")
    cmds = data.get("cmds")
    if not device or not isinstance(device, dict):
        return jsonify({"result": None, "error": "device object required"}), 400
    if not cmds or not isinstance(cmds, list):
        return jsonify({"result": None, "error": "cmds array required"}), 400
    ip = (device.get("ip") or "").strip()
    if not ip:
        return jsonify({"result": None, "error": "device ip is required"}), 400
    cred_name = (device.get("credential") or "").strip()
    username, password = _get_credentials(cred_name, app.config["SECRET_KEY"], creds)
    if not username and not password:
        return jsonify({"result": None, "error": f"no credential for '{cred_name}'"}), 400
    # Substitute enable password into any {"cmd": "enable", "input": "..."} entry
    cmds_out = []
    for c in cmds:
        if isinstance(c, dict) and (c.get("cmd") or "").strip().lower() == "enable":
            cmds_out.append({"cmd": "enable", "input": password or ""})
        elif isinstance(c, dict):
            cmds_out.append(c)
        else:
            cmds_out.append(str(c).strip() if c is not None else "")
    from backend.runners import arista_eapi
    results, err = arista_eapi.run_cmds(ip, username, password, cmds_out, timeout=60)
    if err:
        return jsonify({"result": None, "error": err}), 200
    return jsonify({"result": results, "error": None})


@app.route("/api/router-devices", methods=["GET"])
def api_router_devices():
    """Return DCI and/or WAN routers for route-map compare. scope=dci|wan|all. Full device dicts."""
    scope = (request.args.get("scope") or "all").strip().lower()
    devs = load_inventory(_inventory_path())
    role_lower = lambda r: (r or "").strip().lower()
    if scope == "dci":
        devices = [d for d in devs if role_lower(d.get("role")) == "dci-router"]
    elif scope == "wan":
        devices = [d for d in devs if role_lower(d.get("role")) == "wan-router"]
    else:
        devices = [d for d in devs if role_lower(d.get("role")) in ("dci-router", "wan-router")]
    return jsonify({"devices": devices})


@app.route("/api/route-map/run", methods=["POST"])
def api_route_map_run():
    """
    Run route-map compare on selected (Arista EOS) devices. Body: { "devices": [ { hostname, ip, vendor, model, credential }, ... ] }.
    Returns: { "ok": bool, "rows": [ { peer_group, route_map_in, route_map_out, hierarchy_in, hierarchy_out, devices }, ... ], "errors": [ { hostname, error }, ... ] }.
    """
    data = request.get_json() or {}
    devices = data.get("devices") or []
    if not isinstance(devices, list) or not devices:
        return jsonify({"ok": False, "rows": [], "errors": [{"error": "devices list required"}]}), 400

    from backend.runners import arista_eapi

    parsed_list = []
    errors = []
    for d in devices:
        hostname = (d.get("hostname") or "").strip()
        ip = (d.get("ip") or "").strip()
        vendor = (d.get("vendor") or "").strip()
        model = (d.get("model") or "").strip()
        cred_name = (d.get("credential") or "").strip()
        if not ip:
            errors.append({"hostname": hostname, "error": "missing ip"})
            continue
        username, password = _get_credentials(cred_name, app.config["SECRET_KEY"], creds)
        if not username and not password:
            errors.append({"hostname": hostname, "error": f"no credential for '{cred_name}'"})
            continue
        is_arista = (vendor or "").lower() in ("arista",) or (model or "").lower() in ("eos",)
        if not is_arista:
            errors.append({"hostname": hostname, "error": "only Arista EOS supported"})
            continue
        results, err = arista_eapi.run_commands(ip, username, password, ["show running-config | json"], timeout=120)
        if err:
            errors.append({"hostname": hostname, "error": err})
            continue
        config = results[0] if results else None
        if not isinstance(config, dict):
            errors.append({"hostname": hostname, "error": "no JSON config"})
            continue
        try:
            parsed = route_map_analysis_module.analyze_router_config(config)
            parsed_list.append({"hostname": hostname, "vendor": vendor, "model": model, "parsed": parsed})
        except Exception as e:
            errors.append({"hostname": hostname, "error": str(e)[:200]})

    rows = route_map_analysis_module.build_unified_bgp_full_table(parsed_list)
    return jsonify({"ok": True, "rows": rows, "errors": errors})


@app.route("/api/inventory", methods=["GET"])
def api_inventory():
    """Full inventory as list (for Inventory page)."""
    devs = load_inventory(_inventory_path())
    return jsonify({"inventory": devs})


def _device_row(d):
    """Normalize request body or dict to one device row (lowercase keys)."""
    if not d or not isinstance(d, dict):
        return None
    row = {}
    for k in INVENTORY_HEADER:
        v = d.get(k) or d.get(k.strip() if isinstance(k, str) else k) or ""
        row[k] = (v.strip() if isinstance(v, str) else (v if v is not None else ""))
    return row


@app.route("/api/inventory/device", methods=["POST"])
def api_inventory_device_add():
    """Add one device. Hostname and IP must be unique."""
    data = request.get_json() or {}
    row = _device_row(data)
    if not row or not (row.get("hostname") or "").strip():
        return jsonify({"error": "hostname is required"}), 400
    hostname = (row.get("hostname") or "").strip()
    ip = (row.get("ip") or "").strip()
    devs = load_inventory(_inventory_path())
    if any((d.get("hostname") or "").strip().lower() == hostname.lower() for d in devs):
        return jsonify({"error": "hostname already exists"}), 400
    if any((d.get("ip") or "").strip() == ip for d in devs if ip):
        return jsonify({"error": "IP address already exists"}), 400
    devs.append(row)
    save_inventory(devs, settings.INVENTORY_PATH)
    return jsonify({"ok": True, "device": row})


@app.route("/api/inventory/device", methods=["PUT"])
def api_inventory_device_update():
    """Update one device. Identify by current_hostname. New hostname and IP must be unique."""
    data = request.get_json() or {}
    current = (data.get("current_hostname") or "").strip()
    if not current:
        return jsonify({"error": "current_hostname is required"}), 400
    row = _device_row(data)
    if not row or not (row.get("hostname") or "").strip():
        return jsonify({"error": "hostname is required"}), 400
    hostname = (row.get("hostname") or "").strip()
    ip = (row.get("ip") or "").strip()
    devs = load_inventory(_inventory_path())
    idx = next((i for i, d in enumerate(devs) if (d.get("hostname") or "").strip() == current), None)
    if idx is None:
        return jsonify({"error": "device not found"}), 404
    if hostname.lower() != current.lower() and any((d.get("hostname") or "").strip().lower() == hostname.lower() for d in devs):
        return jsonify({"error": "hostname already exists"}), 400
    if ip and any((d.get("ip") or "").strip() == ip for i, d in enumerate(devs) if i != idx):
        return jsonify({"error": "IP address already exists"}), 400
    devs[idx] = row
    save_inventory(devs, settings.INVENTORY_PATH)
    return jsonify({"ok": True, "device": row})


@app.route("/api/inventory/device", methods=["DELETE"])
def api_inventory_device_delete():
    """Delete one device by hostname or IP."""
    hostname = (request.args.get("hostname") or "").strip()
    ip = (request.args.get("ip") or "").strip()
    if not hostname and not ip:
        return jsonify({"error": "hostname or ip required"}), 400
    devs = load_inventory(_inventory_path())
    if hostname:
        devs = [d for d in devs if (d.get("hostname") or "").strip() != hostname]
    else:
        devs = [d for d in devs if (d.get("ip") or "").strip() != ip]
    if len(devs) == len(load_inventory(_inventory_path())):
        return jsonify({"error": "device not found"}), 404
    save_inventory(devs, settings.INVENTORY_PATH)
    return jsonify({"ok": True})


@app.route("/api/inventory/import", methods=["POST"])
def api_inventory_import():
    """Append rows from body. Body: { rows: [ { hostname, ip, ... }, ... ] }. Unique hostname and IP enforced."""
    data = request.get_json() or {}
    rows = data.get("rows")
    if not isinstance(rows, list):
        return jsonify({"error": "rows array required"}), 400
    devs = load_inventory(_inventory_path())
    existing_hostnames = {(d.get("hostname") or "").strip().lower() for d in devs}
    existing_ips = {(d.get("ip") or "").strip() for d in devs if (d.get("ip") or "").strip()}
    added = 0
    skipped = []
    for r in rows:
        row = _device_row(r)
        if not row or not (row.get("hostname") or "").strip():
            skipped.append({"row": r, "reason": "missing hostname"})
            continue
        hostname = (row.get("hostname") or "").strip()
        ip = (row.get("ip") or "").strip()
        if hostname.lower() in existing_hostnames:
            skipped.append({"row": row, "reason": "hostname already exists"})
            continue
        if ip and ip in existing_ips:
            skipped.append({"row": row, "reason": "IP already exists"})
            continue
        devs.append(row)
        existing_hostnames.add(hostname.lower())
        existing_ips.add(ip)
        added += 1
    save_inventory(devs, settings.INVENTORY_PATH)
    return jsonify({"ok": True, "added": added, "skipped": skipped})


@app.route("/api/commands", methods=["GET"])
def api_commands():
    """Commands applicable to a device. Query: vendor, model, role."""
    vendor = (request.args.get("vendor") or "").strip()
    model = (request.args.get("model") or "").strip()
    role = (request.args.get("role") or "").strip()
    commands = cmd_loader.get_commands_for_device(vendor, model, role)
    return jsonify({"commands": commands})


@app.route("/api/parsers/fields", methods=["GET"])
def api_parsers_fields():
    """All parser field names (for dynamic table columns)."""
    fields = cmd_loader.get_all_parser_field_names()
    return jsonify({"fields": fields})


@app.route("/api/parsers/<command_id>", methods=["GET"])
def api_parser(command_id):
    """Parser config for a command id."""
    cfg = cmd_loader.get_parser(command_id)
    if cfg is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(cfg)


def _single_ping(ip: str, timeout_sec: int = 2) -> bool:
    """One ping to ip. Returns True if reachable."""
    try:
        if platform.system().lower() == "windows":
            out = subprocess.run(
                ["ping", "-n", "1", "-w", str(timeout_sec * 1000), ip],
                capture_output=True,
                timeout=timeout_sec + 1,
            )
        else:
            out = subprocess.run(
                ["ping", "-c", "1", "-W", str(timeout_sec), ip],
                capture_output=True,
                timeout=timeout_sec + 1,
            )
        return out.returncode == 0
    except Exception:
        return False


@app.route("/api/ping", methods=["POST"])
def api_ping():
    """
    Ping devices: first successful ping -> green; else up to 5 attempts.
    Body: { "devices": [ {"hostname": "...", "ip": "..."}, ... ] }.
    Returns { "results": [ {"hostname", "ip", "reachable": true|false }, ... ] }.
    """
    data = request.get_json() or {}
    devices = data.get("devices") or []
    if not isinstance(devices, list):
        return jsonify({"error": "devices must be a list"}), 400
    max_attempts = 5
    results = []
    for d in devices:
        hostname = (d.get("hostname") or "").strip()
        ip = (d.get("ip") or "").strip()
        if not ip:
            results.append({"hostname": hostname, "ip": ip, "reachable": False})
            continue
        reachable = False
        for _ in range(max_attempts):
            if _single_ping(ip):
                reachable = True
                break
        results.append({"hostname": hostname, "ip": ip, "reachable": reachable})
    return jsonify({"results": results})


# ---------- Pre/Post Run ----------
def _run_devices(devices: list) -> list:
    """Run commands for each device; return list of device_results."""
    results = []
    for d in devices:
        r = run_device_commands(d, app.config["SECRET_KEY"], creds)
        results.append(r)
    return results


@app.route("/api/run/device", methods=["POST"])
def api_run_device():
    """
    Run commands for a single device. Body: { "device": { hostname, ip, vendor, model, role, credential } }.
    Returns { device_result } (one element of device_results).
    """
    data = request.get_json() or {}
    device = data.get("device")
    if not device or not isinstance(device, dict):
        return jsonify({"error": "device object required"}), 400
    result = run_device_commands(device, app.config["SECRET_KEY"], creds)
    return jsonify({"device_result": result})


@app.route("/api/transceiver", methods=["POST"])
def api_transceiver():
    """
    Run transceiver + interface status on each device; merge status/last_flap into rows.
    Body: { "devices": [ { hostname, ip, vendor, model, role, credential }, ... ] }.
    Returns { "rows": [ { hostname, ip, interface, serial, type, status, last_flap, ... }, ... ], "errors": [...] }.
    """
    data = request.get_json() or {}
    devices = data.get("devices") or []
    if not isinstance(devices, list):
        return jsonify({"error": "devices array required"}), 400
    all_rows = []
    errors = []
    for device in devices:
        hostname = (device.get("hostname") or device.get("ip") or "unknown").strip()
        result = run_device_commands(
            device, app.config["SECRET_KEY"], creds, command_id_filter="transceiver"
        )
        if result.get("error"):
            errors.append({"hostname": hostname, "error": result["error"]})
            continue
        flat = result.get("parsed_flat") or {}
        transceiver_rows = flat.get("transceiver_rows")
        status_by_interface = {}
        status_result = run_device_commands(
            device, app.config["SECRET_KEY"], creds, command_id_filter="interface_status"
        )
        if not status_result.get("error"):
            status_flat = status_result.get("parsed_flat") or {}
            for s in status_flat.get("interface_status_rows") or []:
                if isinstance(s, dict) and s.get("interface"):
                    status_by_interface[str(s["interface"]).strip()] = {
                        "state": s.get("state") or "-",
                        "last_link_flapped": s.get("last_link_flapped") or "-",
                        "in_errors": s.get("in_errors") or "-",
                    }
        description_by_interface = {}
        desc_result = run_device_commands(
            device, app.config["SECRET_KEY"], creds, command_id_filter="interface_description"
        )
        if not desc_result.get("error"):
            desc_flat = desc_result.get("parsed_flat") or {}
            description_by_interface = desc_flat.get("interface_descriptions") or {}
            if not isinstance(description_by_interface, dict):
                description_by_interface = {}
        if isinstance(transceiver_rows, list):
            for row in transceiver_rows:
                if not isinstance(row, dict):
                    continue
                iface = str(row.get("interface") or "").strip()
                st = status_by_interface.get(iface) or {}
                desc = description_by_interface.get(iface) if isinstance(description_by_interface, dict) else ""
                all_rows.append({
                    "hostname": result.get("hostname") or hostname,
                    "ip": result.get("ip") or device.get("ip") or "",
                    "interface": iface,
                    "description": desc if desc else "-",
                    "serial": row.get("serial") or "",
                    "type": row.get("type") or "",
                    "manufacturer": row.get("manufacturer") or "",
                    "temp": row.get("temp") or "",
                    "tx_power": row.get("tx_power") or "",
                    "rx_power": row.get("rx_power") or "",
                    "status": st.get("state") or "-",
                    "last_flap": st.get("last_link_flapped") or "-",
                    "in_errors": st.get("in_errors") or "-",
                })
        if not transceiver_rows and not result.get("error"):
            errors.append({"hostname": hostname, "error": "no transceiver data (unsupported or no optics)"})
    return jsonify({"rows": all_rows, "errors": errors})


# Intent-based blocklist: substrings that indicate config/write intent (read-only safeguard per .cursorrules §6)
_READONLY_BLOCKLIST = (
    "conf t", "configure terminal", "config t", "config terminal",
    "| write", "write mem", "write memory", "copy run start",
    "| append", "| tee", "terminal no monitor", "logging buffered",
)


def _allowed_custom_command(cmd: str) -> bool:
    """Only allow commands that start with 'show' or 'dir' and do not suggest config/write intent."""
    c = (cmd or "").strip().lower()
    if not (c.startswith("show") or c.startswith("dir")):
        return False
    for block in _READONLY_BLOCKLIST:
        if block in c:
            return False
    return True


@app.route("/api/custom-command", methods=["POST"])
def api_custom_command():
    """
    Run a single custom command on a device via SSH. Command must start with 'show' or 'dir'.
    Body: { "device": { hostname, ip, credential, ... }, "command": "show ..." }.
    Returns { "output": str or null, "error": str or null }.
    """
    data = request.get_json() or {}
    device = data.get("device")
    command = (data.get("command") or "").strip()
    if not device or not isinstance(device, dict):
        return jsonify({"error": "device object required"}), 400
    if not command:
        return jsonify({"error": "command is required"}), 400
    if not _allowed_custom_command(command):
        return jsonify({"error": "only commands starting with 'show' or 'dir' are allowed"}), 400
    ip = (device.get("ip") or "").strip()
    if not ip:
        return jsonify({"error": "device ip is required"}), 400
    cred_name = (device.get("credential") or "").strip()
    username, password = _get_credentials(cred_name, app.config["SECRET_KEY"], creds)
    if not username and not password:
        return jsonify({"output": None, "error": f"no credential for '{cred_name}'"})
    from backend.runners import ssh_runner
    output, err = ssh_runner.run_command(ip, username, password, command)
    if err:
        return jsonify({"output": None, "error": err})
    return jsonify({"output": output or "", "error": None})


@app.route("/api/find-leaf", methods=["POST"])
def api_find_leaf():
    """
    Find leaf and interface for an IP. Body: { "ip": "1.2.3.4" }.
    Only IP format is accepted. Uses devices with tag 'leaf-search'.
    Returns find_leaf result: found, leaf_hostname, leaf_ip, interface, vendor, etc.
    """
    data = request.get_json() or {}
    search_ip = (data.get("ip") or "").strip()
    if not search_ip:
        return jsonify({"error": "ip is required"}), 400
    try:
        result = find_leaf_module.find_leaf(
            search_ip,
            app.config["SECRET_KEY"],
            creds,
            inventory_path=_inventory_path(),
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({
            "found": False,
            "error": str(e),
            "leaf_hostname": "",
            "leaf_ip": "",
            "interface": "",
            "vendor": "",
            "remote_vtep_addr": "",
            "physical_iod": "",
            "checked_devices": [],
        })


@app.route("/api/find-leaf-check-device", methods=["POST"])
def api_find_leaf_check_device():
    """Check a single leaf-search device for the IP. Body: { "ip": "1.2.3.4", "hostname": "SW1" } or "device_ip"."""
    data = request.get_json() or {}
    search_ip = (data.get("ip") or "").strip()
    hostname = (data.get("hostname") or "").strip()
    device_ip = (data.get("device_ip") or "").strip()
    identifier = hostname or device_ip
    if not search_ip:
        return jsonify({"found": False, "error": "ip is required", "checked_hostname": identifier}), 400
    if not identifier:
        return jsonify({"found": False, "error": "hostname or device_ip is required", "checked_hostname": ""}), 400
    try:
        result = find_leaf_module.find_leaf_check_device(
            search_ip,
            identifier,
            app.config["SECRET_KEY"],
            creds,
            inventory_path=_inventory_path(),
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({
            "found": False,
            "error": str(e),
            "checked_hostname": identifier,
            "leaf_hostname": "",
            "leaf_ip": "",
            "interface": "",
            "vendor": "",
            "fabric": "",
            "hall": "",
            "site": "",
        })


@app.route("/api/nat-lookup", methods=["POST"])
def api_nat_lookup():
    """
    NAT Lookup: body { "src_ip": "1.2.3.4", "dest_ip": "8.8.8.8" }.
    Finds leaf for src_ip (fabric/site), then queries Palo Alto firewalls with tag 'natlookup'
    in that fabric/site. Returns rule name and translated IP(s).
    """
    data = request.get_json() or {}
    src_ip = (data.get("src_ip") or "").strip()
    dest_ip = (data.get("dest_ip") or "").strip() or "8.8.8.8"
    debug = bool(data.get("debug"))
    fabric = (data.get("fabric") or "").strip() or None
    site = (data.get("site") or "").strip() or None
    leaf_checked_devices = data.get("leaf_checked_devices") if isinstance(data.get("leaf_checked_devices"), list) else None
    if not src_ip:
        return jsonify({"ok": False, "error": "src_ip is required"}), 400
    try:
        result = nat_lookup_module.nat_lookup(
            src_ip,
            dest_ip,
            app.config["SECRET_KEY"],
            creds,
            inventory_path=_inventory_path(),
            debug=debug,
            fabric=fabric,
            site=site,
            leaf_checked_devices=leaf_checked_devices,
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e),
            "fabric": "",
            "site": "",
            "rule_name": "",
            "translated_ips": [],
            "firewall_hostname": "",
            "firewall_ip": "",
            "leaf_checked_devices": [],
            "debug": None,
        })


# ---------- BGP Looking Glass (RIPEStat, RPKI, PeeringDB) ----------
def _bgp_resource():
    prefix = (request.args.get("prefix") or "").strip()
    asn = (request.args.get("asn") or "").strip()
    if prefix:
        return prefix
    if asn:
        return f"AS{asn}" if not asn.upper().startswith("AS") else asn
    return None


@app.route("/api/bgp/status", methods=["GET"])
def api_bgp_status():
    """BGP status: routing-status + RPKI + PeeringDB AS name. Query: prefix=1.1.1.0/24 or asn=13335."""
    resource = _bgp_resource()
    if not resource:
        return jsonify({"error": "prefix or asn required"}), 400
    return jsonify(bgp_lg.get_bgp_status(resource))


@app.route("/api/bgp/history", methods=["GET"])
def api_bgp_history():
    """BGP routing history for diff. Query: prefix=... or asn=..."""
    resource = _bgp_resource()
    if not resource:
        return jsonify({"error": "prefix or asn required"}), 400
    return jsonify(bgp_lg.get_bgp_history(resource))


@app.route("/api/bgp/visibility", methods=["GET"])
def api_bgp_visibility():
    """BGP visibility (RIS probes). Query: prefix=... or asn=..."""
    resource = _bgp_resource()
    if not resource:
        return jsonify({"error": "prefix or asn required"}), 400
    return jsonify(bgp_lg.get_bgp_visibility(resource))


@app.route("/api/bgp/looking-glass", methods=["GET"])
def api_bgp_looking_glass():
    """Looking Glass: RRCs and peers seeing the resource. Query: prefix=... or asn=..."""
    resource = _bgp_resource()
    if not resource:
        return jsonify({"error": "prefix or asn required"}), 400
    return jsonify(bgp_lg.get_bgp_looking_glass(resource))


@app.route("/api/bgp/bgplay", methods=["GET"])
def api_bgp_bgplay():
    """BGP play: path changes in time window. Query: prefix=... or asn=..., optional starttime, endtime (ISO8601 or Unix)."""
    resource = _bgp_resource()
    if not resource:
        return jsonify({"error": "prefix or asn required"}), 400
    starttime = (request.args.get("starttime") or "").strip() or None
    endtime = (request.args.get("endtime") or "").strip() or None
    return jsonify(bgp_lg.get_bgp_play(resource, starttime=starttime, endtime=endtime))


@app.route("/api/bgp/as-info", methods=["GET"])
def api_bgp_as_info():
    """AS holder/company name from RIPEStat. Query: asn=9121."""
    asn = (request.args.get("asn") or "").strip()
    if not asn:
        return jsonify({"error": "asn required"}), 400
    return jsonify(bgp_lg.get_bgp_as_info(asn))


@app.route("/api/bgp/announced-prefixes", methods=["GET"])
def api_bgp_announced_prefixes():
    """Prefixes announced by an AS (RIPEStat). Query: asn=9121."""
    asn = (request.args.get("asn") or "").strip()
    if not asn:
        return jsonify({"error": "asn required"}), 400
    return jsonify(bgp_lg.get_bgp_announced_prefixes(asn))


def _wan_rtr_has_bgp_as(config_output, asn_str: str, is_json: bool) -> bool:
    """Check if running config contains 'router bgp <asn>' (AS number only)."""
    import re
    asn_str = (asn_str or "").strip()
    if not asn_str or not asn_str.isdigit():
        return False
    pattern = re.compile(r"router\s+bgp\s+" + re.escape(asn_str) + r"(?:\s|$)", re.I)
    if is_json:
        data = config_output if isinstance(config_output, dict) else None
        if not data:
            return False
        cmds = data.get("cmds") or data
        if not isinstance(cmds, dict):
            return False
        for key in cmds:
            if isinstance(key, str) and pattern.search(key):
                return True
        return False
    text = config_output if isinstance(config_output, str) else ""
    return bool(pattern.search(text))


@app.route("/api/bgp/wan-rtr-match", methods=["GET"])
def api_bgp_wan_rtr_match():
    """
    Search WAN Router devices for 'router bgp <AS>' in running-config.
    Query: asn=13335 (digits only). Returns { matches: [ { hostname, fabric, site }, ... ], error?: str }.
    """
    asn_raw = (request.args.get("asn") or "").strip().replace("AS", "").replace("as", "").strip()
    if not asn_raw or not asn_raw.isdigit():
        return jsonify({"matches": [], "error": "asn required (digits only)"}), 400
    devs = load_inventory(_inventory_path())
    role_lower = lambda r: (r or "").strip().lower().replace(" ", "-")
    wan = [d for d in devs if role_lower(d.get("role")) == "wan-router"]
    matches = []
    for d in wan:
        hostname = (d.get("hostname") or "").strip() or (d.get("ip") or "?")
        ip = (d.get("ip") or "").strip()
        cred_name = (d.get("credential") or "").strip()
        vendor = (d.get("vendor") or "").strip()
        model = (d.get("model") or "").strip()
        if not ip:
            continue
        username, password = _get_credentials(cred_name, app.config["SECRET_KEY"], creds)
        if not username and not password:
            continue
        found = False
        try:
            if (vendor or "").lower() in ("arista",) or (model or "").lower() in ("eos",):
                from backend.runners import arista_eapi
                results, err = arista_eapi.run_commands(ip, username, password, ["show running-config | json"], timeout=90)
                if not err and results:
                    cfg = results[0] if isinstance(results[0], dict) else None
                    if cfg:
                        found = _wan_rtr_has_bgp_as(cfg, asn_raw, is_json=True)
            else:
                from backend.runners import ssh_runner
                out, err = ssh_runner.run_command(ip, username, password, "show running-config", timeout=60)
                if not err and out:
                    found = _wan_rtr_has_bgp_as(out, asn_raw, is_json=False)
        except Exception:
            pass
        if found:
            matches.append({
                "hostname": hostname,
                "fabric": (d.get("fabric") or "").strip() or "—",
                "site": (d.get("site") or "").strip() or "—",
            })
    return jsonify({"matches": matches})


@app.route("/api/run/pre/create", methods=["POST"])
def api_run_pre_create():
    """
    Create a PRE run from devices + device_results (e.g. after running devices one-by-one).
    Body: { "devices": [...], "device_results": [...], "name": "optional" }. Returns { run_id, run_created_at }.
    Persists report to disk (gzip) for Saved reports list.
    """
    data = request.get_json() or {}
    devices = data.get("devices") or []
    device_results = data.get("device_results") or []
    name = (data.get("name") or "").strip() or None
    if not isinstance(devices, list) or not devices:
        return jsonify({"error": "devices list required"}), 400
    if not isinstance(device_results, list) or len(device_results) != len(devices):
        return jsonify({"error": "device_results length must match devices"}), 400
    run_id = str(uuid.uuid4())
    created_at = __import__("datetime").datetime.utcnow().isoformat() + "Z"
    _run_state[run_id] = {
        "phase": "PRE",
        "devices": devices,
        "device_results": device_results,
        "created_at": created_at,
    }
    try:
        _persist_report(run_id, name, created_at, devices, device_results, post_created_at=None, post_device_results=None, comparison=None)
    except Exception:
        pass
    return jsonify({"run_id": run_id, "run_created_at": created_at})


@app.route("/api/run/pre/restore", methods=["POST"])
def api_run_pre_restore():
    """
    Restore a PRE run from saved report (e.g. after page refresh or server restart).
    Body: { "run_id": "...", "devices": [...], "device_results": [...], "created_at": "..." }.
    Puts the run back into server state so POST can be run. Returns { "ok": true }.
    """
    data = request.get_json() or {}
    run_id = (data.get("run_id") or "").strip()
    devices = data.get("devices") or []
    device_results = data.get("device_results") or []
    created_at = data.get("created_at") or __import__("datetime").datetime.utcnow().isoformat() + "Z"
    if not run_id:
        return jsonify({"error": "run_id required"}), 400
    if not isinstance(devices, list) or not devices:
        return jsonify({"error": "devices list required"}), 400
    if not isinstance(device_results, list) or len(device_results) != len(devices):
        return jsonify({"error": "device_results length must match devices"}), 400
    _run_state[run_id] = {
        "phase": "PRE",
        "devices": devices,
        "device_results": device_results,
        "created_at": created_at,
    }
    return jsonify({"ok": True})


@app.route("/api/run/pre", methods=["POST"])
def api_run_pre():
    """
    Run PRE: execute commands for each device, parse, store. Body: { "devices": [ { hostname, ip, vendor, model, role, credential }, ... ] }.
    Returns { run_id, phase: "PRE", device_results }.
    """
    data = request.get_json() or {}
    devices = data.get("devices") or []
    if not isinstance(devices, list) or not devices:
        return jsonify({"error": "devices list required"}), 400
    run_id = str(uuid.uuid4())
    device_results = _run_devices(devices)
    created_at = __import__("datetime").datetime.utcnow().isoformat() + "Z"
    _run_state[run_id] = {
        "phase": "PRE",
        "devices": devices,
        "device_results": device_results,
        "created_at": created_at,
    }
    return jsonify({"run_id": run_id, "phase": "PRE", "device_results": device_results, "run_created_at": created_at})


@app.route("/api/run/post", methods=["POST"])
def api_run_post():
    """
    Run POST: body { "run_id": "..." }. Re-runs same devices as PRE, returns POST results and comparison.
    """
    data = request.get_json() or {}
    run_id = (data.get("run_id") or "").strip()
    if not run_id or run_id not in _run_state:
        return jsonify({"error": "run_id not found or expired"}), 404
    pre_run = _run_state[run_id]
    if pre_run["phase"] != "PRE":
        return jsonify({"error": "run_id is not a PRE run"}), 400
    devices = pre_run["devices"]
    device_results = _run_devices(devices)
    comparison = []
    for i, (pre_r, post_r) in enumerate(zip(pre_run["device_results"], device_results)):
        pre_flat = pre_r.get("parsed_flat") or {}
        post_flat = post_r.get("parsed_flat") or {}
        diff = {}
        all_keys = set(pre_flat) | set(post_flat)
        for k in all_keys:
            pv, pov = pre_flat.get(k), post_flat.get(k)
            if pv != pov:
                diff[k] = {"pre": pv, "post": pov}
        comparison.append({
            "hostname": pre_r.get("hostname"),
            "ip": pre_r.get("ip"),
            "diff": diff,
        })
    post_created_at = __import__("datetime").datetime.utcnow().isoformat() + "Z"
    _run_state[run_id]["post_device_results"] = device_results
    _run_state[run_id]["comparison"] = comparison
    _run_state[run_id]["post_created_at"] = post_created_at
    return jsonify({
        "run_id": run_id,
        "phase": "POST",
        "device_results": device_results,
        "pre_device_results": pre_run.get("device_results"),
        "comparison": comparison,
        "run_created_at": pre_run.get("created_at"),
        "post_created_at": post_created_at,
    })


@app.route("/api/run/post/complete", methods=["POST"])
def api_run_post_complete():
    """
    Complete POST run with pre-computed device_results (e.g. from frontend running devices in parallel).
    Body: { "run_id": "...", "device_results": [...] }. Returns same as api_run_post.
    """
    data = request.get_json() or {}
    run_id = (data.get("run_id") or "").strip()
    device_results = data.get("device_results") or []
    if not run_id or run_id not in _run_state:
        return jsonify({"error": "run_id not found or expired"}), 404
    pre_run = _run_state[run_id]
    if pre_run["phase"] != "PRE":
        return jsonify({"error": "run_id is not a PRE run"}), 400
    devices = pre_run["devices"]
    if len(device_results) != len(devices):
        return jsonify({"error": "device_results length must match PRE devices"}), 400
    comparison = []
    for i, (pre_r, post_r) in enumerate(zip(pre_run["device_results"], device_results)):
        pre_flat = pre_r.get("parsed_flat") or {}
        post_flat = post_r.get("parsed_flat") or {}
        diff = {}
        all_keys = set(pre_flat) | set(post_flat)
        for k in all_keys:
            pv, pov = pre_flat.get(k), post_flat.get(k)
            if pv != pov:
                diff[k] = {"pre": pv, "post": pov}
        comparison.append({
            "hostname": pre_r.get("hostname"),
            "ip": pre_r.get("ip"),
            "diff": diff,
        })
    post_created_at = __import__("datetime").datetime.utcnow().isoformat() + "Z"
    _run_state[run_id]["post_device_results"] = device_results
    _run_state[run_id]["comparison"] = comparison
    _run_state[run_id]["post_created_at"] = post_created_at
    try:
        loaded = _load_report(run_id)
        name = (loaded.get("name") or "pre_report") if isinstance(loaded, dict) else "pre_report"
        _persist_report(
            run_id,
            name,
            pre_run.get("created_at"),
            pre_run.get("devices") or [],
            pre_run.get("device_results") or [],
            post_created_at=post_created_at,
            post_device_results=device_results,
            comparison=comparison,
        )
    except Exception:
        pass
    return jsonify({
        "run_id": run_id,
        "phase": "POST",
        "device_results": device_results,
        "pre_device_results": pre_run.get("device_results"),
        "comparison": comparison,
        "run_created_at": pre_run.get("created_at"),
        "post_created_at": post_created_at,
    })


@app.route("/api/diff", methods=["POST"])
def api_diff():
    """
    Body: { "pre": "text", "post": "text" }. Returns unified diff (git diff style).
    """
    data = request.get_json() or {}
    pre_text = (data.get("pre") or "").strip()
    post_text = (data.get("post") or "").strip()
    import difflib
    diff = difflib.unified_diff(
        (pre_text or "").splitlines(keepends=True),
        (post_text or "").splitlines(keepends=True),
        fromfile="PRE",
        tofile="POST",
        lineterm="",
    )
    out = "".join(diff)
    return jsonify({"diff": out})


@app.route("/api/run/result/<run_id>", methods=["GET"])
def api_run_result(run_id):
    """Get stored run result (PRE or POST)."""
    if run_id not in _run_state:
        return jsonify({"error": "not found"}), 404
    return jsonify(_run_state[run_id])


@app.route("/api/reports", methods=["GET"])
def api_reports_list():
    """List saved reports (from disk index). Returns { reports: [ { run_id, name, created_at, post_created_at }, ... ] }."""
    try:
        entries = _load_reports_index()
        return jsonify({"reports": entries})
    except Exception:
        return jsonify({"reports": []})


@app.route("/api/reports/<run_id>", methods=["GET"])
def api_report_get(run_id):
    """Get a single saved report by run_id (from disk). Optionally ?restore=1 to also load into run state for POST."""
    run_id = (run_id or "").strip()
    if not run_id:
        return jsonify({"error": "run_id required"}), 400
    try:
        report = _load_report(run_id)
    except Exception:
        return jsonify({"error": "failed to load report"}), 500
    if report is None:
        return jsonify({"error": "report not found"}), 404
    if request.args.get("restore") == "1":
        _run_state[run_id] = {
            "phase": "POST" if report.get("post_created_at") else "PRE",
            "devices": report.get("devices") or [],
            "device_results": report.get("device_results") or [],
            "created_at": report.get("created_at"),
            "post_device_results": report.get("post_device_results"),
            "post_created_at": report.get("post_created_at"),
            "comparison": report.get("comparison"),
        }
    return jsonify(report)


@app.route("/api/reports/<run_id>", methods=["DELETE"])
def api_report_delete(run_id):
    """Delete a saved report from disk."""
    run_id = (run_id or "").strip()
    if not run_id:
        return jsonify({"error": "run_id required"}), 400
    try:
        _delete_report(run_id)
        return jsonify({"ok": True})
    except Exception:
        return jsonify({"error": "failed to delete"}), 500


# ---------- Credentials (name = inventory credential field) ----------
@app.route("/api/credentials", methods=["GET"])
def api_credentials_list():
    list_ = creds.list_credentials(app.config["SECRET_KEY"])
    return jsonify({"credentials": list_})


@app.route("/api/credentials", methods=["POST"])
def api_credentials_create():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    method = (data.get("method") or "").strip().lower()
    if not name:
        return jsonify({"error": "name is required"}), 400
    if method not in ("api_key", "basic"):
        return jsonify({"error": "method must be api_key or basic"}), 400
    try:
        if method == "api_key":
            creds.set_credential(
                name, method, app.config["SECRET_KEY"], api_key=data.get("api_key") or ""
            )
        else:
            creds.set_credential(
                name,
                method,
                app.config["SECRET_KEY"],
                username=data.get("username") or "",
                password=data.get("password") or "",
            )
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/credentials/<name>", methods=["DELETE"])
def api_credentials_delete(name):
    if creds.delete_credential(name):
        return jsonify({"ok": True})
    return jsonify({"error": "not found"}), 404


@app.route("/api/credentials/<name>/validate", methods=["POST"])
def api_credentials_validate(name):
    """Validate credential by attempting login to the first device in inventory that uses it."""
    if not creds.get_credential(name.strip(), app.config["SECRET_KEY"]):
        return jsonify({"ok": False, "error": "Credential not found"}), 404
    devs = load_inventory(_inventory_path())
    cred_lower = (name or "").strip().lower()
    candidates = [d for d in devs if (d.get("credential") or "").strip().lower() == cred_lower]
    if not candidates:
        return jsonify({
            "ok": False,
            "device": None,
            "error": "No device in inventory uses this credential",
        })
    device = candidates[0]
    hostname = (device.get("hostname") or device.get("ip") or "unknown").strip()
    result = run_device_commands(device, app.config["SECRET_KEY"], creds)
    if result.get("error"):
        return jsonify({
            "ok": False,
            "device": hostname,
            "error": result["error"],
        })
    ran = [c for c in (result.get("commands") or []) if not c.get("error") and c.get("raw") is not None]
    if not ran:
        return jsonify({
            "ok": False,
            "device": hostname,
            "error": "No applicable commands for this device; cannot validate login.",
        })
    parsed = result.get("parsed_flat") or {}
    uptime = (parsed.get("Uptime") or "").strip()
    payload = {
        "ok": True,
        "device": result.get("hostname") or hostname,
        "message": "Logged in to {}.".format(result.get("hostname") or hostname),
    }
    if uptime:
        payload["uptime"] = uptime
    return jsonify(payload)


# ---------- Health ----------
@app.route("/api/health", methods=["GET"])
def api_health():
    return jsonify({"status": "ok"})


# ---------- SPA fallback (when frontend is built) ----------
@app.route("/")
def index():
    if app.static_folder and os.path.isfile(os.path.join(app.static_folder, "index.html")):
        return send_from_directory(app.static_folder, "index.html")
    return jsonify({"message": "Pergen API. Use /api/* routes."})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
