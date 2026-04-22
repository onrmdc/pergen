"""
Pergen parser layer.

Phase-7 deliverable: ``ParserEngine`` is the OOD façade over the
existing ``backend.parse_output.parse_output`` function plus the YAML
parser registry in ``backend/config/parsers.yaml``.

The legacy module (``backend.parse_output``) is kept untouched — the
engine simply caches the YAML registry and delegates each
``parse(command_id, raw_output)`` call to ``parse_output(command_id,
raw_output, parser_config)``.  Behaviour is anchored by the 22 golden
parser snapshots from phase 1.
"""
from backend.parsers.engine import ParserEngine

__all__ = ["ParserEngine"]
