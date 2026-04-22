"""Cisco NX-API result/body envelope unwrap helper.

Many NX-OS parsers receive raw output that has been wrapped at one or
more of these layers:

1. ``[ {…} ]`` — list (NX-API ``ins_api`` format wraps every command
   in a list of result objects).
2. ``{"result": [...]}`` — single ``result`` envelope.
3. ``{"body": "<json string>"}`` — body is a JSON string that needs a
   second pass through ``json.loads``.

This helper unwraps all three layers in one call and returns the inner
data dict (or whatever scalar/None it ended up resolving to). Audit
HIGH-3 (python-reviewer): de-duplicates the same 8-line preamble
that was previously inlined in 5 NX-OS parser modules.
"""

from __future__ import annotations

import json
from typing import Any


def cisco_unwrap_body(raw_output: Any) -> Any:
    """Unwrap the optional list / ``result`` / ``body`` envelopes.

    Returns the inner dict if found, else the closest non-envelope
    object (which the caller should still type-check before use).
    Pure function — never raises on malformed input; returns whatever
    layer it could safely resolve.
    """
    data: Any = raw_output

    # Layer 1: top-level result wrapper
    if isinstance(raw_output, dict) and "result" in raw_output:
        r = raw_output["result"]
        data = r[0] if isinstance(r, list) and r else r

    # Layer 2: bare list (NX-API ins_api)
    if isinstance(raw_output, list) and raw_output and isinstance(raw_output[0], dict):
        data = raw_output[0]

    # Layer 3: stringified body
    body = data.get("body") if isinstance(data, dict) else None
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except (json.JSONDecodeError, ValueError, TypeError):
            body = None
    if body is not None and isinstance(body, dict):
        data = body

    return data


__all__ = ["cisco_unwrap_body"]
