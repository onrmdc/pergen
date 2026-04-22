"""Generic field-config parser engine.

Replaces the ``else`` branch of the legacy ``parse_output()`` dispatcher
with a focused class. Walks ``parser_config["fields"]`` and applies one
of: ``json_path`` (with optional ``count``, ``count_where``,
``key_prefix``+``value_key``), ``regex`` (with optional ``count``), or
the ``format_template`` second pass.

Behaviour is preserved byte-for-byte — see
``docs/refactor/parse_output_split.md`` (Phase 4).
"""

from __future__ import annotations

import json
from typing import Any

from backend.parsers.common.counters import (
    _count_from_json,
    _count_where,
    _get_from_dict_by_key_prefix,
)
from backend.parsers.common.formatting import _apply_value_subtract_and_suffix
from backend.parsers.common.json_path import _get_path
from backend.parsers.common.regex_helpers import _count_regex_lines, _extract_regex


class GenericFieldEngine:
    """Stateless engine that walks a list of field configs over raw output.

    The engine is intentionally a thin object with one ``apply()`` method
    so that the upcoming ``backend.parsers.dispatcher`` (Phase 5) can
    route to it as the default branch when ``custom_parser`` is unset.
    """

    def apply(self, raw_output: Any, parser_config: dict) -> dict[str, Any]:
        """Apply ``parser_config["fields"]`` to ``raw_output``.

        Inputs
        ------
        raw_output : ``dict`` (API JSON) or ``str`` (SSH text)
        parser_config : the full parser config dict (must contain a
            ``fields`` list — empty/missing returns ``{}``).

        Outputs
        -------
        ``dict`` of ``field_name -> value`` (string or number).
        """
        if parser_config is None:
            return {}
        fields = parser_config.get("fields") or []
        result: dict[str, Any] = {}

        # Normalize: if raw_output is str, try parse as JSON for json_path
        data: Any = raw_output
        text = raw_output if isinstance(raw_output, str) else ""
        if isinstance(raw_output, str) and raw_output.strip().startswith("{"):
            try:
                data = json.loads(raw_output)
            except (json.JSONDecodeError, ValueError, TypeError):  # narrow audit HIGH-1
                pass

        for f in fields:
            name = (f.get("name") or "").strip()
            if not name:
                continue
            if f.get("format_template") and f.get("format_fields"):
                continue  # applied after loop
            if f.get("json_path"):
                self._apply_json_path_field(f, name, data, result)
            elif f.get("regex"):
                self._apply_regex_field(f, name, text, result)

        # Apply format_template fields (e.g. ISIS "up/ready", BGP "est/total")
        for f in fields:
            if not f.get("format_template") or not f.get("format_fields"):
                continue
            name = (f.get("name") or "").strip()
            if not name:
                continue
            fmt_fields = f["format_fields"]
            try:
                result[name] = f["format_template"].format(
                    **{k: result.get(k, "") for k in fmt_fields}
                )
            except (KeyError, ValueError):
                result[name] = ""
        return result

    # ------------------------------------------------------------------ #
    # branch helpers — small enough to fit on one screen each
    # ------------------------------------------------------------------ #
    @staticmethod
    def _apply_json_path_field(
        f: dict, name: str, data: Any, result: dict[str, Any]
    ) -> None:
        count_where = f.get("count_where")
        key_prefix = f.get("key_prefix") or f.get("count_key_prefix")
        if f.get("count"):
            flatten_inner = f.get("flatten_inner_path")
            if isinstance(count_where, dict) and count_where:
                result[name] = _count_where(
                    data,
                    f["json_path"],
                    count_where,
                    key_prefix=key_prefix,
                    key_prefix_exclude=f.get("count_key_prefix_exclude"),
                    flatten_inner_path=flatten_inner,
                )
            else:
                result[name] = _count_from_json(
                    data, f["json_path"], flatten_inner_path=flatten_inner
                )
        elif f.get("key_prefix") and f.get("value_key"):
            div = f.get("value_divide") or f.get("value_divisor") or 1
            val = _get_from_dict_by_key_prefix(
                data, f["json_path"], f["key_prefix"], f["value_key"], divisor=div
            )
            if val is None:
                result[name] = None
            elif f.get("value_suffix"):
                num = float(val) if not isinstance(val, (int, float)) else val
                result[name] = (
                    str(int(num)) if num == int(num) else str(round(num, 2))
                ) + f.get("value_suffix")
            else:
                result[name] = val if isinstance(val, (int, float)) else str(val)
        else:
            val = _get_path(data, f["json_path"])
            _apply_value_subtract_and_suffix(f, val, result, name)

    @staticmethod
    def _apply_regex_field(
        f: dict, name: str, text: str, result: dict[str, Any]
    ) -> None:
        if f.get("count"):
            result[name] = _count_regex_lines(text, f["regex"])
        else:
            result[name] = _extract_regex(text, f["regex"]) or ""


__all__ = ["GenericFieldEngine"]
