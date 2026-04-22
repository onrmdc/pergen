"""Shared parser utilities used across vendor and domain modules.

These helpers are deliberately small, pure, and free of vendor-specific
knowledge so that they can be reused by every parser in
``backend.parsers.<vendor>.<domain>``.

Public surface (all also re-exported via ``backend.parse_output`` for
back-compat — see ``docs/refactor/parse_output_split.md``):

* json_path: dict/list path lookups and nested flattening
* counters: counts derived from JSON structures
* regex_helpers: regex-based extraction and counting
* formatting: value formatting helpers (suffix, subtract, power decimals)
* duration: relative-time and HH:MM:SS parsing
* arista_envelope: unwrapping the Arista eAPI result wrapper
"""
