"""
Flask app for network device panel.

Run from repo root: ``FLASK_APP=backend.app flask run``.

Phase 12 of the app.py decomposition shrinks this module to its
minimum viable shape: define the global ``app`` Flask instance (so
existing operator invocations keep working), wire ``SECRET_KEY``,
init the credential store, and export the legacy ``_*`` helper
aliases that in-tree callers still resolve through ``backend.app``.

Every route now lives in a per-domain blueprint under
``backend/blueprints/`` and is registered through
``backend/app_factory.py::create_app`` — see
``docs/refactor/app_decomposition.md`` for the full inventory.
"""
from __future__ import annotations

import os
import sys

# Ensure project root is on path when running as ``flask run``.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402

from backend import credential_store as creds  # noqa: E402

# --------------------------------------------------------------------------- #
# Legacy helper re-exports                                                    #
# --------------------------------------------------------------------------- #
# Phase 2 moved these helpers into focused ``backend.utils.*`` modules.
# They are re-exported here under the original ``_*`` names because some
# in-tree callers (and one regression test) still resolve them as
# ``backend.app._foo``. Keeping the shim costs nothing and removes the
# need for a second migration sweep.
from backend.utils.bgp_helpers import wan_rtr_has_bgp_as as _wan_rtr_has_bgp_as  # noqa: E402, F401
from backend.utils.interface_status import (  # noqa: E402, F401
    cisco_interface_detailed_trace as _cisco_interface_detailed_trace,
)
from backend.utils.interface_status import (  # noqa: E402, F401
    iface_status_lookup as _iface_status_lookup,
)
from backend.utils.interface_status import (  # noqa: E402, F401
    interface_status_trace as _interface_status_trace,
)
from backend.utils.interface_status import (  # noqa: E402, F401
    merge_cisco_detailed_flap as _merge_cisco_detailed_flap,
)
from backend.utils.ping import MAX_PING_DEVICES as _MAX_PING_DEVICES  # noqa: E402, F401
from backend.utils.ping import single_ping as _single_ping  # noqa: E402, F401
from backend.utils.transceiver_display import (  # noqa: E402, F401
    transceiver_errors_display as _transceiver_errors_display,
)
from backend.utils.transceiver_display import (  # noqa: E402, F401
    transceiver_last_flap_display as _transceiver_last_flap_display,
)

# --------------------------------------------------------------------------- #
# Flask app construction                                                      #
# --------------------------------------------------------------------------- #
_static = os.path.join(os.path.dirname(__file__), "static")
app = Flask(__name__, static_folder=_static if os.path.isdir(_static) else None)

# Audit C2/R7: SECRET_KEY uses the SAME sentinel as
# ``backend.config.app_config.DEFAULT_SECRET_KEY`` so
# ``ProductionConfig.validate()`` catches a single placeholder, not two.
# The factory's ``_apply_config`` overwrites this with the
# environment-resolved value before any route runs.
from backend.config.app_config import DEFAULT_SECRET_KEY  # noqa: E402

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or DEFAULT_SECRET_KEY

# Init credential DB on startup (once).
creds.init_db(app.config["SECRET_KEY"])


# --------------------------------------------------------------------------- #
# Routes are registered exclusively through ``backend.app_factory.create_app``
# via the per-domain blueprints listed in
# ``docs/refactor/app_decomposition.md``. ``backend.app`` itself only
# defines the ``app`` global so legacy ``FLASK_APP=backend.app`` still works.
# --------------------------------------------------------------------------- #


if __name__ == "__main__":
    # Audit (Security review H-3): the legacy ``backend/app`` shim no
    # longer registers any routes — running ``python -m backend.app``
    # used to bind ``0.0.0.0`` with ZERO routes AND bypass the API
    # token gate (which is mounted by ``create_app``). That created a
    # latent foot-gun: a future contributor restoring ``from
    # backend.blueprints import …`` here would expose every route
    # publicly without auth. Refuse to bind unless the operator has
    # explicitly opted in and pin the bind to localhost by default.
    _bind_host = os.environ.get("PERGEN_DEV_BIND_HOST", "127.0.0.1")
    if _bind_host != "127.0.0.1" and os.environ.get("PERGEN_DEV_ALLOW_PUBLIC_BIND") != "1":
        raise SystemExit(
            f"backend.app __main__ refuses to bind '{_bind_host}' without "
            "PERGEN_DEV_ALLOW_PUBLIC_BIND=1. Use the documented "
            "entrypoint: FLASK_APP=backend.app_factory:create_app "
            "flask run."
        )
    app.run(host=_bind_host, port=int(os.environ.get("PORT", 5000)))
