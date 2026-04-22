"""
``ParserEngine`` — class wrapper around the parser registry and the
legacy ``parse_output`` dispatcher.

Why a class?
------------
* Routes / services should depend on a single object whose interface
  fits in their constructor signature, not on a dynamically loaded
  module-level dict + a free function.
* Test doubles can supply an in-memory registry (no YAML file needed).
* Unknown command ids return ``{}`` instead of crashing the device
  loop — the engine is the authoritative "do I know how to parse
  this?" check.

The engine's parse method delegates to the legacy ``parse_output``
function imported as ``_legacy_parse_output`` so unit tests can patch
the symbol without touching the original module.
"""
from __future__ import annotations

import logging
from typing import Any

import yaml

from backend.parsers.dispatcher import Dispatcher

_log = logging.getLogger("app.parsers.engine")

# Module-level dispatcher singleton. Kept here (rather than per-instance)
# so test code can patch ``backend.parsers.engine._DEFAULT_DISPATCHER``
# without touching every engine instance, and so engines built ad-hoc
# (e.g. in tests) automatically pick it up.
_DEFAULT_DISPATCHER = Dispatcher()


def _legacy_parse_output(command_id: str, raw_output: Any, parser_config: dict) -> dict:
    """Compatibility trampoline.

    Pre-refactor, ``ParserEngine.parse`` delegated to
    ``backend.parse_output.parse_output``. After the parse_output split
    (see ``docs/refactor/parse_output_split.md``) we route via the
    ``Dispatcher`` directly. This wrapper preserves the legacy patch
    target ``backend.parsers.engine._legacy_parse_output`` that
    ``tests/test_parser_engine.py`` and other test sites depend on.
    """
    return _DEFAULT_DISPATCHER.parse(command_id, raw_output, parser_config)


class ParserEngine:
    """Read-only registry + delegating parser façade."""

    def __init__(self, registry: dict[str, dict[str, Any]] | None = None) -> None:
        """
        Inputs
        ------
        registry : ``{command_id: parser_config_dict}``.  Defaults to
            an empty dict so an engine can be built without any
            parsers (every ``parse`` call returns ``{}``).

        Outputs
        -------
        ``ParserEngine`` instance.
        """
        self._registry: dict[str, dict[str, Any]] = dict(registry or {})

    # ------------------------------------------------------------------ #
    # construction helpers
    # ------------------------------------------------------------------ #
    @classmethod
    def from_yaml(cls, yaml_path: str) -> ParserEngine:
        """Load the registry from a YAML file (dict-of-dicts shape)."""
        with open(yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            raise ValueError(f"parsers YAML must be a mapping, got {type(data).__name__}")
        clean: dict[str, dict[str, Any]] = {}
        for key, val in data.items():
            if isinstance(val, dict):
                clean[str(key)] = val
            else:
                _log.warning("ignoring non-dict parser entry: %s", key)
        return cls(clean)

    # ------------------------------------------------------------------ #
    # introspection
    # ------------------------------------------------------------------ #
    def has(self, command_id: str) -> bool:
        """Return True iff a parser config exists for *command_id*."""
        return (command_id or "") in self._registry

    def get_config(self, command_id: str) -> dict[str, Any] | None:
        """Return the parser-config dict for *command_id* or None."""
        return self._registry.get(command_id or "")

    def command_ids(self) -> list[str]:
        """Return the registered command ids in alphabetical order."""
        return sorted(self._registry.keys())

    # ------------------------------------------------------------------ #
    # parsing
    # ------------------------------------------------------------------ #
    def parse(self, command_id: str, raw_output: Any) -> dict[str, Any]:
        """
        Parse *raw_output* using the config registered for *command_id*.

        Inputs
        ------
        command_id : registered parser identifier.
        raw_output : ``dict`` (API JSON) or ``str`` (SSH text).

        Outputs
        -------
        ``dict`` of parsed fields, or ``{}`` if no config is registered.

        Security
        --------
        The legacy ``parse_output`` swallows internal exceptions and
        returns whatever it managed to extract — the engine preserves
        that contract so a malformed device response cannot crash the
        device loop.
        """
        cfg = self.get_config(command_id)
        if cfg is None:
            return {}
        try:
            return _legacy_parse_output(command_id, raw_output, cfg) or {}
        except Exception as exc:  # pragma: no cover - defensive
            _log.warning("parser %s raised %s; returning empty dict", command_id, exc)
            return {}
