"""
Per-domain Flask Blueprints.

Each Blueprint:

* Lives in its own file ``backend/blueprints/<domain>_bp.py``.
* Defines a top-level ``<domain>_bp = Blueprint(...)`` symbol.
* Registers its routes with explicit full paths (``/api/...``) — never
  with a Blueprint ``url_prefix`` (avoids accidental path duplication).
* Holds NO business logic — calls into ``backend/services`` (phase 8).

Phase-9 ships ``inventory_bp`` and ``notepad_bp`` (full extraction from
the legacy ``backend/app.py``); credentials, reports, run, transceiver,
bgp, find_leaf, and nat blueprints follow in subsequent phases.
"""
from backend.blueprints.bgp_bp import bgp_bp
from backend.blueprints.commands_bp import commands_bp
from backend.blueprints.credentials_bp import credentials_bp
from backend.blueprints.device_commands_bp import device_commands_bp
from backend.blueprints.health_bp import health_bp
from backend.blueprints.inventory_bp import inventory_bp
from backend.blueprints.network_lookup_bp import network_lookup_bp
from backend.blueprints.network_ops_bp import network_ops_bp
from backend.blueprints.notepad_bp import notepad_bp
from backend.blueprints.reports_bp import reports_bp
from backend.blueprints.runs_bp import runs_bp
from backend.blueprints.transceiver_bp import transceiver_bp

__all__ = [
    "bgp_bp",
    "commands_bp",
    "credentials_bp",
    "device_commands_bp",
    "health_bp",
    "inventory_bp",
    "network_lookup_bp",
    "network_ops_bp",
    "notepad_bp",
    "reports_bp",
    "runs_bp",
    "transceiver_bp",
]
