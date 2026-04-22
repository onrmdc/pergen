"""Arista vendor-specific parsers (eAPI / `... | json` shapes).

Phase 2 of the parse_output refactor — see
``docs/refactor/parse_output_split.md``.

Each module owns one logical parser, copied verbatim from the legacy
``backend/parse_output.py``. Cross-cutting helpers live in
``backend.parsers.common``.
"""
