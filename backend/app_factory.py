"""
Application Factory for Pergen.

Phase-4 deliverable.

This is a *wrapping* factory: the legacy ``backend/app.py`` module is
imported once (it builds the global ``app`` instance and registers every
route as a side effect), and ``create_app`` then layers the new
configuration / logging / request middleware on top.

Why wrapping rather than full Blueprint extraction?
---------------------------------------------------
``backend/app.py`` is a 1700+ line module with ~60 routes that all use the
module-level ``app`` global.  A single-PR rewrite into Blueprints would
risk silent route drift (different ``url_for`` keys, different error
handling, missing ``before_request`` order) which our 107 golden tests
would catch only after the damage is done.  By wrapping, we ship the
factory, the new config classes, and the logging stack today; subsequent
phases (5–9) peel routes out into Blueprints incrementally as services
are introduced.

The factory remains the canonical entry point — ``backend/app.py`` keeps
its module-level ``app`` so existing ``FLASK_APP=backend.app flask run``
invocations keep working.

Initialisation order
--------------------
1. Load the requested config class from ``CONFIG_MAP``.
2. Validate the config (production refuses default SECRET_KEY).
3. Import the legacy ``backend.app`` module (registers all routes).
4. Apply the new config values onto ``app.config``.
5. Configure logging *after* the config is on the app (so
   ``LOG_LEVEL`` / ``LOG_FORMAT`` / ``LOG_FILE`` are honoured).
6. Mount ``RequestLogger.init_app(app)`` middleware.
7. Re-init credential DB (in case ``SECRET_KEY`` changed for tests).
8. Return ``app``.
"""
from __future__ import annotations

import logging
from typing import Any

from flask import Flask

from backend.config.app_config import CONFIG_MAP, BaseConfig
from backend.logging_config import LoggingConfig
from backend.request_logging import RequestLogger

_log = logging.getLogger("app.factory")

# Audit C-1: minimum API token length when the gate is active.
_MIN_API_TOKEN_LENGTH = 32


def create_app(config_name: str = "default") -> Flask:
    """
    Build (or wrap) the Pergen Flask application.

    Inputs
    ------
    config_name : ``"development"`` / ``"testing"`` / ``"production"`` /
                  ``"default"``.  Anything else falls back to ``default``.

    Outputs
    -------
    A fully configured ``Flask`` instance with:
      * ``app.config`` populated from the chosen config class,
      * structured logging mounted on the root logger,
      * per-request middleware (UUID4 request id, X-Request-ID header,
        slow-request WARN),
      * every legacy route from ``backend/app.py`` already registered.

    Security
    --------
    ``ProductionConfig.validate()`` is invoked before any side effects so
    a misconfigured production deploy fails *before* binding to a port.
    """
    cfg_cls = CONFIG_MAP.get(config_name) or CONFIG_MAP["default"]
    cfg: BaseConfig = cfg_cls()
    cfg.validate()

    # --- Step 3: import legacy module (this registers all routes). ------- #
    # ``importlib.import_module`` guarantees we resolve through ``sys.modules``
    # rather than the stale ``backend.app`` attribute on the ``backend``
    # package — important for tests that pop modules between calls.
    import importlib

    legacy_app_module = importlib.import_module("backend.app")
    app: Flask = legacy_app_module.app

    # --- Step 4: copy config values onto app.config. --------------------- #
    _apply_config(app, cfg)
    # Audit C-1: stash the config name early so the token gate can detect
    # production mode and fail-closed BEFORE any side effect.
    app.config["CONFIG_NAME"] = config_name

    # --- Step 5: structured logging. ------------------------------------- #
    LoggingConfig.configure(app)
    _log.debug("logging configured for %s", config_name)

    # --- Step 6: per-request middleware (idempotent). -------------------- #
    if not getattr(app, "_pergen_request_logger_mounted", False):
        RequestLogger.init_app(app)
        app._pergen_request_logger_mounted = True  # type: ignore[attr-defined]

    # --- Step 6b: optional API token gate (audit C1). -------------------- #
    # When ``PERGEN_API_TOKEN`` (env) or ``app.config['PERGEN_API_TOKEN']``
    # is set, every /api/* request must carry a matching ``X-API-Token``
    # header. Liveness probes (/api/health, /api/v2/health) and the SPA
    # fallback (/) are exempt. Backwards-compatible default: gate is
    # disabled, every endpoint stays open.
    _install_api_token_gate(app)

    # --- Step 7: build & register the OOD service layer. ----------------- #
    _register_services(app)

    # --- Step 8: register per-domain Blueprints (idempotent). ------------ #
    _register_blueprints(app)

    # --- Step 9: re-init credential store with the (possibly new) key. --- #
    try:
        from backend import credential_store as creds

        creds.init_db(app.config["SECRET_KEY"])
    except Exception as e:  # pragma: no cover - cred store is best-effort
        _log.warning("credential store re-init failed: %s", e)

    _log.info("Pergen app ready (config=%s)", config_name)
    return app


def _parse_actor_tokens(raw: str) -> dict[str, str]:
    """Parse ``PERGEN_API_TOKENS=actor1:tok1,actor2:tok2`` into a mapping.

    Audit C-2: per-actor accountability. Empty entries, missing colons,
    whitespace-only segments and duplicate actors are silently dropped
    so a malformed env var can never widen access. Returns ``{actor: token}``.
    """
    out: dict[str, str] = {}
    for part in (raw or "").split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        actor, _, token = part.partition(":")
        actor = actor.strip()
        token = token.strip()
        if actor and token and actor not in out:
            out[actor] = token
    return out


def _install_api_token_gate(app: Flask) -> None:
    """Install an ``X-API-Token`` gate on every /api/* route.

    Audit C-1 mitigation (fail-closed in production) + C-2 (per-actor
    accountability):

    Token sources, in priority order:

    1. ``PERGEN_API_TOKENS`` env var (or app.config) — preferred. Format:
       ``actor1:token1,actor2:token2``. Each token is a distinct
       operator identity. The matched actor is stored on
       ``flask.g.actor`` so audit log lines can record who did what.
    2. ``PERGEN_API_TOKEN`` env var (or app.config) — single shared
       bearer (legacy). Sets ``flask.g.actor = "shared"``.

    Activation:

    * **Production** (``CONFIG_NAME == "production"``): a token MUST be
      configured (either form). ``create_app`` raises ``RuntimeError``
      on start otherwise — refusing to boot beats serving an open API.
      All tokens must be ``_MIN_API_TOKEN_LENGTH`` chars or longer.
    * **Non-production**: gate is opt-in. When no tokens are set, the
      gate is a no-op and a one-shot WARN is logged on first request.

    Exempt paths (always open for liveness probes / SPA bootstrap):
        /api/health, /api/v2/health, /
    """
    import hmac
    import os as _os

    from flask import g, jsonify, request

    if getattr(app, "_pergen_token_gate_mounted", False):
        return

    _exempt = {"/api/health", "/api/v2/health", "/"}
    _min_len = _MIN_API_TOKEN_LENGTH

    def _resolve_tokens() -> dict[str, str]:
        """Return ``{actor: token}`` from current env+config (re-read each request)."""
        raw_multi = (
            _os.environ.get("PERGEN_API_TOKENS")
            or app.config.get("PERGEN_API_TOKENS")
            or ""
        )
        tokens = _parse_actor_tokens(raw_multi)
        single = (
            _os.environ.get("PERGEN_API_TOKEN")
            or app.config.get("PERGEN_API_TOKEN")
            or ""
        )
        if single and "shared" not in tokens:
            tokens["shared"] = single
        return tokens

    # Fail-closed validation for production (evaluated at create_app time):
    if app.config.get("CONFIG_NAME") == "production":
        prod_tokens = _resolve_tokens()
        if not prod_tokens:
            raise RuntimeError(
                "PERGEN_API_TOKEN(S) must be set in production "
                "(refusing to start with an open API). "
                "Set PERGEN_API_TOKENS=actor1:tok1,actor2:tok2 (preferred) or "
                f"PERGEN_API_TOKEN=<random>. Each token must be at least "
                f"{_min_len} characters."
            )
        for actor, tok in prod_tokens.items():
            if len(tok) < _min_len:
                raise RuntimeError(
                    f"PERGEN API token for actor {actor!r} must be at least "
                    f"{_min_len} characters in production."
                )

    @app.before_request
    def _enforce_api_token():
        tokens = _resolve_tokens()
        if not tokens:
            # Non-production only path. Emit a one-shot WARN so operators
            # in dev see the open posture in their logs.
            if not getattr(app, "_pergen_open_api_warned", False):
                _log.warning(
                    "PERGEN_API_TOKEN(S) not set — /api/* is OPEN (dev/test only)"
                )
                app._pergen_open_api_warned = True  # type: ignore[attr-defined]
            g.actor = "anonymous"
            return None
        if request.path in _exempt or not request.path.startswith("/api/"):
            return None
        supplied = request.headers.get("X-API-Token", "")
        # Constant-time comparison to neutralise timing oracles. Try every
        # configured token; the FIRST match wins. We compare against every
        # token even after a hit so timing leaks the *number* of configured
        # actors but not which one matched.
        matched_actor: str | None = None
        for actor, token in tokens.items():
            if hmac.compare_digest(supplied, token):
                matched_actor = matched_actor or actor
        if matched_actor is not None:
            g.actor = matched_actor
            return None
        return jsonify({"error": "missing or invalid X-API-Token header"}), 401

    app._pergen_token_gate_mounted = True  # type: ignore[attr-defined]


def _register_blueprints(app: Flask) -> None:
    """Mount per-domain Blueprints, skipping any already registered."""
    from backend.blueprints import (
        bgp_bp,
        commands_bp,
        credentials_bp,
        device_commands_bp,
        health_bp,
        inventory_bp,
        network_lookup_bp,
        network_ops_bp,
        notepad_bp,
        reports_bp,
        runs_bp,
        transceiver_bp,
    )

    for bp in (
        health_bp,
        inventory_bp,
        notepad_bp,
        commands_bp,
        network_ops_bp,
        credentials_bp,
        bgp_bp,
        network_lookup_bp,
        transceiver_bp,
        device_commands_bp,
        runs_bp,
        reports_bp,
    ):
        if bp.name not in app.blueprints:
            app.register_blueprint(bp)


def _register_services(app: Flask) -> None:
    """Build the OOD service layer and stash each instance in
    ``app.extensions`` for the per-domain Blueprints to consume.

    Idempotent — if a service is already registered (e.g. on a second
    ``create_app`` call against the same legacy ``app`` global) the
    existing instance is left in place.

    Path resolution for the inventory CSV mirrors the legacy
    ``backend/app.py:_inventory_path`` helper: prefer the configured
    path, fall back to the bundled example only if the primary file is
    absent.
    """
    import os

    from backend.config import settings
    from backend.parsers import ParserEngine
    from backend.repositories import (
        CredentialRepository,
        InventoryRepository,
        NotepadRepository,
        ReportRepository,
    )
    from backend.runners import RunnerFactory
    from backend.security.encryption import EncryptionService
    from backend.services import (
        CredentialService,
        DeviceService,
        InventoryService,
        NotepadService,
        ReportService,
        RunStateStore,
    )

    ext = app.extensions

    # ---------- Inventory ----------
    # Phase 3: re-register the service when the configured CSV path
    # changes (e.g. between test cases that point ``PERGEN_INVENTORY_PATH``
    # at different temp files). Without this guard the cached service
    # keeps pointing at the previous test's CSV → write-side endpoints
    # mutate the wrong file → cross-test bleed.
    inv_path = settings.INVENTORY_PATH
    if not os.path.isfile(inv_path) and os.path.isfile(settings.EXAMPLE_INVENTORY_PATH):
        inv_path = settings.EXAMPLE_INVENTORY_PATH
    cached_inv = ext.get("inventory_service")
    if cached_inv is None or getattr(cached_inv, "csv_path", None) != inv_path:
        ext["inventory_service"] = InventoryService(InventoryRepository(inv_path))

    # ---------- Notepad ----------
    cached_np = ext.get("notepad_service")
    if cached_np is None or getattr(getattr(cached_np, "_repo", None), "_dir", None) != settings.INSTANCE_DIR:
        ext["notepad_service"] = NotepadService(NotepadRepository(settings.INSTANCE_DIR))

    # ---------- Reports ----------
    reports_dir = os.path.join(settings.INSTANCE_DIR, "reports")
    cached_rep = ext.get("report_service")
    if cached_rep is None or getattr(getattr(cached_rep, "_repo", None), "_reports_dir", None) != reports_dir:
        ext["report_service"] = ReportService(ReportRepository(reports_dir))

    # ---------- Credentials (NEW key derivation; isolated DB to avoid
    # mismatches with the legacy ``backend.credential_store`` Fernet
    # blob during the migration window). -----------------------------------
    if "credential_service" not in ext:
        cred_db = app.config.get("CREDENTIAL_DB_PATH") or os.path.join(
            settings.INSTANCE_DIR, "credentials_v2.db"
        )
        # Audit H8: tighten umask before creating the parent directory
        # so the credential DB can never inherit world-readable mode.
        # CredentialRepository.create_schema() further enforces 0o600 on
        # the file itself.
        prev_umask = os.umask(0o077)
        try:
            os.makedirs(os.path.dirname(cred_db) or ".", exist_ok=True)
        finally:
            os.umask(prev_umask)
        enc = EncryptionService.from_secret(app.config["SECRET_KEY"])
        cred_repo = CredentialRepository(cred_db, enc)
        cred_repo.create_schema()
        ext["credential_service"] = CredentialService(cred_repo)

    # ---------- Device orchestrator ----------
    if "device_service" not in ext:
        ext["device_service"] = DeviceService(
            credential_service=ext["credential_service"],
            runner_factory=RunnerFactory(),
            parser_engine=ParserEngine(),
        )

    # ---------- Run-state store (Phase 11) ----------
    # Replaces the module-global ``_run_state`` dict in the legacy
    # backend.app. A fresh store is bound when the report directory
    # changes (i.e. across tests with different instance dirs) so
    # cross-test state cannot leak.
    cached_store = ext.get("run_state_store")
    if cached_store is None:
        ext["run_state_store"] = RunStateStore()


def _apply_config(app: Flask, cfg: BaseConfig) -> None:
    """Mirror dataclass attributes onto ``app.config``."""
    payload: dict[str, Any] = {
        "SECRET_KEY": cfg.SECRET_KEY,
        "DEBUG": cfg.DEBUG,
        "TESTING": cfg.TESTING,
        "CREDENTIAL_DB_PATH": cfg.CREDENTIAL_DB_PATH,
        "LOG_LEVEL": cfg.LOG_LEVEL,
        "LOG_FORMAT": cfg.LOG_FORMAT,
        "LOG_FILE": cfg.LOG_FILE,
        "LOG_SLOW_MS": cfg.LOG_SLOW_MS,
        "START_SCHEDULER": cfg.START_SCHEDULER,
        "MAX_CONTENT_LENGTH": cfg.MAX_CONTENT_LENGTH,
    }
    app.config.update(payload)
