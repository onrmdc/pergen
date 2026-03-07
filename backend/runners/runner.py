"""
Run commands for a device: resolve credential, get command set, execute (API or SSH), parse output.
"""
from typing import Any

from backend.config import commands_loader as cmd_loader
from backend import parse_output as parse_output_module


def _hostname_from_api_output(obj: Any) -> str:
    """Extract hostname from command API response (dict or list of dicts). Prefer API over inventory."""
    if isinstance(obj, dict):
        for key in ("hostname", "host_name", "Hostname"):
            val = obj.get(key)
            if val and isinstance(val, str):
                return val.strip()
        for v in obj.values():
            if isinstance(v, dict):
                found = _hostname_from_api_output(v)
                if found:
                    return found
    elif isinstance(obj, list) and obj:
        return _hostname_from_api_output(obj[0])
    return ""


def _get_credentials(credential_name: str, secret_key: str, cred_store_module) -> tuple[str, str]:
    """Resolve username, password from credential store by name."""
    c = cred_store_module.get_credential(credential_name.strip(), secret_key)
    if not c:
        return "", ""
    if c.get("method") == "api_key":
        return "", c.get("api_key") or ""
    return c.get("username") or "", c.get("password") or ""


def run_device_commands(
    device: dict,
    secret_key: str,
    cred_store_module,
    command_id_filter: str | None = None,
) -> dict[str, Any]:
    """
    Run all applicable commands for the device. Returns:
    {
      "hostname": "...",
      "ip": "...",
      "error": null or str,
      "commands": [
        { "command_id": "...", "raw": ..., "parsed": {...}, "error": null or str }
      ],
      "parsed_flat": { "field_name": value, ... }  # merged for table
    }
    """
    hostname = (device.get("hostname") or "").strip()
    ip = (device.get("ip") or "").strip()
    vendor = (device.get("vendor") or "").strip()
    model = (device.get("model") or "").strip()
    role = (device.get("role") or "").strip()
    cred_name = (device.get("credential") or "").strip()

    out = {
        "hostname": "",  # filled only from API response, not from inventory
        "ip": ip,
        "vendor": vendor,
        "model": model,
        "error": None,
        "commands": [],
        "parsed_flat": {},
    }
    if not ip:
        out["error"] = "missing ip"
        return out

    username, password = _get_credentials(cred_name, secret_key, cred_store_module)
    if not username and not password:
        out["error"] = f"no credential for '{cred_name}'"
        return out

    commands = cmd_loader.get_commands_for_device(vendor, model, role)
    if not commands:
        return out
    if command_id_filter:
        commands = [c for c in commands if (c.get("id") or "").lower().find(command_id_filter.lower()) >= 0]
        if not commands:
            return out

    for cmd_cfg in commands:
        cid = cmd_cfg.get("id") or ""
        entry = {"command_id": cid, "raw": None, "parsed": {}, "error": None}
        method = (cmd_cfg.get("method") or "").lower()
        raw_output = None
        err = None

        if method == "api":
            api_spec = cmd_cfg.get("api") or {}
            path = (api_spec.get("path") or "").strip()
            cmds = api_spec.get("commands") or []
            if not cmds:
                entry["error"] = "no commands in api spec"
                out["commands"].append(entry)
                continue
            if "command-api" in path or path == "/command-api":
                from backend.runners import arista_eapi
                results, err = arista_eapi.run_commands(ip, username, password, cmds)
                if err:
                    entry["error"] = err
                elif results:
                    raw_output = results[0] if len(results) == 1 else results
            elif "ins" in path or path == "/ins":
                from backend.runners import cisco_nxapi
                results, err = cisco_nxapi.run_commands(ip, username, password, cmds)
                if err:
                    entry["error"] = err
                elif results:
                    raw_output = results[0] if len(results) == 1 else results
            else:
                entry["error"] = f"unknown api path: {path}"
        elif method == "ssh":
            ssh_spec = cmd_cfg.get("ssh") or {}
            cmd = (ssh_spec.get("command") or "").strip()
            if not cmd:
                entry["error"] = "no command in ssh spec"
                out["commands"].append(entry)
                continue
            from backend.runners import ssh_runner
            raw_output, err = ssh_runner.run_command(ip, username, password, cmd)
            if err:
                entry["error"] = err
        else:
            entry["error"] = f"unknown method: {method}"
            out["commands"].append(entry)
            continue

        if err:
            out["commands"].append(entry)
            continue

        entry["raw"] = raw_output
        api_hostname = _hostname_from_api_output(raw_output)
        if api_hostname:
            out["hostname"] = api_hostname
        parser_cfg = cmd_loader.get_parser(cid)
        if parser_cfg:
            parsed = parse_output_module.parse_output(cid, raw_output, parser_cfg)
            entry["parsed"] = parsed
            for k, v in parsed.items():
                out["parsed_flat"][k] = v
        out["commands"].append(entry)

    return out
