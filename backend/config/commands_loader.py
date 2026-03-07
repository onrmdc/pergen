"""
Load commands.yaml and parsers.yaml. Resolve command set for a device (vendor, model, role).
"""
import os
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None

_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
_commands_cache: list[dict] | None = None
_parsers_cache: dict[str, dict] | None = None


def _load_yaml(name: str) -> Any:
    path = os.path.join(_CONFIG_DIR, name)
    if not os.path.isfile(path) or not yaml:
        return {} if "parsers" in name else []
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or ({} if "parsers" in name else [])


def get_commands_config() -> list[dict]:
    """Return full commands list from commands.yaml."""
    global _commands_cache
    if _commands_cache is None:
        data = _load_yaml("commands.yaml")
        _commands_cache = data.get("commands", []) if isinstance(data, dict) else []
    return _commands_cache


def get_parsers_config() -> dict[str, dict]:
    """Return full parsers dict (command_id -> parser config) from parsers.yaml."""
    global _parsers_cache
    if _parsers_cache is None:
        data = _load_yaml("parsers.yaml")
        _parsers_cache = data if isinstance(data, dict) else {}
    return _parsers_cache


def _normalize(s: str) -> str:
    return (s or "").strip().lower()


def get_commands_for_device(vendor: str, model: str, role: str) -> list[dict]:
    """
    Return list of command configs applicable to this device.
    Match vendor (and optionally model) and role; empty roles list means all roles.
    """
    commands = get_commands_config()
    v = _normalize(vendor)
    m = _normalize(model)
    r = _normalize(role)
    out = []
    for cmd in commands:
        cmd_v = _normalize(cmd.get("vendor") or "")
        cmd_m = _normalize(cmd.get("model") or "")
        if cmd_v and cmd_v != v:
            continue
        if cmd_m and cmd_m != m:
            continue
        roles = cmd.get("roles") or []
        if roles and r and not any(_normalize(ro) == r for ro in roles):
            continue
        out.append(cmd)
    return out


def get_parser(command_id: str) -> dict | None:
    """Return parser config for command_id, or None."""
    parsers = get_parsers_config()
    return parsers.get((command_id or "").strip())


def get_all_parser_field_names() -> list[str]:
    """Return sorted unique field names across all parsers (for dynamic table columns)."""
    parsers = get_parsers_config()
    names = set()
    for cfg in parsers.values():
        for f in (cfg.get("fields") or []):
            n = (f.get("name") or "").strip()
            if n:
                names.add(n)
    return sorted(names)
