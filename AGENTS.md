# Everything Claude Code (ECC) — Agent Instructions

This is a **production-ready AI coding plugin** providing 28 specialized agents, 125 skills, 60 commands, and automated hook workflows for software development.

**Version:** 1.9.0

## Core Principles

1. **Agent-First** — Delegate to specialized agents for domain tasks
2. **Test-Driven** — Write tests before implementation, 80%+ coverage required
3. **Security-First** — Never compromise on security; validate all inputs
4. **Immutability** — Always create new objects, never mutate existing ones
5. **Plan Before Execute** — Plan complex features before writing code

## Available Agents

| Agent | Purpose | When to Use |
|-------|---------|-------------|
| planner | Implementation planning | Complex features, refactoring |
| architect | System design and scalability | Architectural decisions |
| tdd-guide | Test-driven development | New features, bug fixes |
| code-reviewer | Code quality and maintainability | After writing/modifying code |
| security-reviewer | Vulnerability detection | Before commits, sensitive code |
| build-error-resolver | Fix build/type errors | When build fails |
| e2e-runner | End-to-end Playwright testing | Critical user flows |
| refactor-cleaner | Dead code cleanup | Code maintenance |
| doc-updater | Documentation and codemaps | Updating docs |
| docs-lookup | Documentation and API reference research | Library/API documentation questions |
| cpp-reviewer | C++ code review | C++ projects |
| cpp-build-resolver | C++ build errors | C++ build failures |
| go-reviewer | Go code review | Go projects |
| go-build-resolver | Go build errors | Go build failures |
| kotlin-reviewer | Kotlin code review | Kotlin/Android/KMP projects |
| kotlin-build-resolver | Kotlin/Gradle build errors | Kotlin build failures |
| database-reviewer | PostgreSQL/Supabase specialist | Schema design, query optimization |
| python-reviewer | Python code review | Python projects |
| java-reviewer | Java and Spring Boot code review | Java/Spring Boot projects |
| java-build-resolver | Java/Maven/Gradle build errors | Java build failures |
| chief-of-staff | Communication triage and drafts | Multi-channel email, Slack, LINE, Messenger |
| loop-operator | Autonomous loop execution | Run loops safely, monitor stalls, intervene |
| harness-optimizer | Harness config tuning | Reliability, cost, throughput |
| rust-reviewer | Rust code review | Rust projects |
| rust-build-resolver | Rust build errors | Rust build failures |
| pytorch-build-resolver | PyTorch runtime/CUDA/training errors | PyTorch build/training failures |
| typescript-reviewer | TypeScript/JavaScript code review | TypeScript/JavaScript projects |

## Agent Orchestration

Use agents proactively without user prompt:
- Complex feature requests → **planner**
- Code just written/modified → **code-reviewer**
- Bug fix or new feature → **tdd-guide**
- Architectural decision → **architect**
- Security-sensitive code → **security-reviewer**
- Multi-channel communication triage → **chief-of-staff**
- Autonomous loops / loop monitoring → **loop-operator**
- Harness config reliability and cost → **harness-optimizer**

Use parallel execution for independent operations — launch multiple agents simultaneously.

## Security Guidelines

**Before ANY commit:**
- No hardcoded secrets (API keys, passwords, tokens)
- All user inputs validated
- SQL injection prevention (parameterized queries)
- XSS prevention (sanitized HTML)
- CSRF protection enabled
- Authentication/authorization verified

**SPA XSS rule (Wave-6 Phase C, enforced by `tests/test_security_innerhtml_lint.py`):** every dynamic `element.innerHTML = ...` write in `backend/static/js/app.js` MUST route every interpolation through `escapeHtml(...)` or the `safeHtml` tagged template — or carry an explicit `// xss-safe: <reason>` annotation on the same or immediately-preceding line. Constant-only assignments and clears (`= ""`) are allowed verbatim. Prefer `textContent` / `dataset` / `setAttribute` whenever no HTML structure is needed. CSS attribute-selector lookups for stored values must use `CSS.escape(value)`. Full policy: [`docs/security/spa_xss_policy.md`](docs/security/spa_xss_policy.md).
- Rate limiting on all endpoints
- Error messages don't leak sensitive data

**Secret management:** NEVER hardcode secrets. Use environment variables or a secret manager. Validate required secrets at startup. Rotate any exposed secrets immediately.

**If security issue found:** STOP → use security-reviewer agent → fix CRITICAL issues → rotate exposed secrets → review codebase for similar issues.

## Coding Style

**Immutability (CRITICAL):** Always create new objects, never mutate. Return new copies with changes applied.

**File organization:** Many small files over few large ones. 200-400 lines typical, 800 max. Organize by feature/domain, not by type. High cohesion, low coupling.

**Error handling:** Handle errors at every level. Provide user-friendly messages in UI code. Log detailed context server-side. Never silently swallow errors.

**Input validation:** Validate all user input at system boundaries. Use schema-based validation. Fail fast with clear messages. Never trust external data.

**Code quality checklist:**
- Functions small (<50 lines), files focused (<800 lines)
- No deep nesting (>4 levels)
- Proper error handling, no hardcoded values
- Readable, well-named identifiers

## Testing Requirements

**Minimum coverage: 80%**

Test types (all required):
1. **Unit tests** — Individual functions, utilities, components
2. **Integration tests** — API endpoints, database operations
3. **E2E tests** — Critical user flows

**TDD workflow (mandatory):**
1. Write test first (RED) — test should FAIL
2. Write minimal implementation (GREEN) — test should PASS
3. Refactor (IMPROVE) — verify coverage 80%+

Troubleshoot failures: check test isolation → verify mocks → fix implementation (not tests, unless tests are wrong).

## Development Workflow

1. **Plan** — Use planner agent, identify dependencies and risks, break into phases
2. **TDD** — Use tdd-guide agent, write tests first, implement, refactor
3. **Review** — Use code-reviewer agent immediately, address CRITICAL/HIGH issues
4. **Capture knowledge in the right place**
   - Personal debugging notes, preferences, and temporary context → auto memory
   - Team/project knowledge (architecture decisions, API changes, runbooks) → the project's existing docs structure
   - If the current task already produces the relevant docs or code comments, do not duplicate the same information elsewhere
   - If there is no obvious project doc location, ask before creating a new top-level file
5. **Commit** — Conventional commits format, comprehensive PR summaries

## Git Workflow

**Commit format:** `<type>: <description>` — Types: feat, fix, refactor, docs, test, chore, perf, ci

**PR workflow:** Analyze full commit history → draft comprehensive summary → include test plan → push with `-u` flag.

## Architecture Patterns

**API response format:** Consistent envelope with success indicator, data payload, error message, and pagination metadata.

**Repository pattern:** Encapsulate data access behind standard interface (findAll, findById, create, update, delete). Business logic depends on abstract interface, not storage mechanism.

**Skeleton projects:** Search for battle-tested templates, evaluate with parallel agents (security, extensibility, relevance), clone best match, iterate within proven structure.

## Performance

**Context management:** Avoid last 20% of context window for large refactoring and multi-file features. Lower-sensitivity tasks (single edits, docs, simple fixes) tolerate higher utilization.

**Build troubleshooting:** Use build-error-resolver agent → analyze errors → fix incrementally → verify after each fix.

## Project Structure

```
agents/          — 28 specialized subagents
skills/          — 125 workflow skills and domain knowledge
commands/        — 60 slash commands
hooks/           — Trigger-based automations
rules/           — Always-follow guidelines (common + per-language)
scripts/         — Cross-platform Node.js utilities
mcp-configs/     — 14 MCP server configurations
tests/           — Test suite
```

## Success Metrics

- All tests pass with 80%+ coverage
- No security vulnerabilities
- Code is readable and maintainable
- Performance is acceptable
- User requirements are met

---

# Pergen-specific notes (project context)

The above sections describe the generic ECC plugin. The repository this
file ships in is **Pergen** — a Flask-based network device panel under
the OOD/TDD refactor on the `refactor/ood-tdd` branch. When working on
this codebase the agent must respect the following project-specific
conventions in addition to the ECC defaults above.

## Pergen architecture (one-liner)

App Factory + 12 blueprints + service layer + repository layer +
RunnerFactory + ParserEngine on top of a 1767-test pytest safety net
(+ 1 strict xfail tracking audit GAP #8) + 45 Vitest + 100 Playwright.
Whole-project coverage **90.79 %**, OOD-scoped **91.34 %**.

Full layered diagram + module reference:
[`ARCHITECTURE.md`](./ARCHITECTURE.md). Per-class function reference:
[`FUNCTIONS_EXPLANATIONS.md`](./FUNCTIONS_EXPLANATIONS.md).

## Pergen env knobs (operationally important)

Most env knobs are documented in [`HOWTOUSE.md`](./HOWTOUSE.md) §3.
The agent should be aware of these in particular when reading config
or writing tests:

| Variable | Default | Purpose | Wave landed |
|----------|---------|---------|-------------|
| `PERGEN_API_TOKEN` / `PERGEN_API_TOKENS` | unset (dev) / **required** (prod, ≥32 chars) | Bearer-token auth gate. Per-actor form: `actor1:tok1,actor2:tok2` resolves to `flask.g.actor` for audit-log accountability. | C-1 / C-2 (audit batch 4) |
| `PERGEN_AUTH_COOKIE_ENABLED` | unset (cookie path off) | When `=1`, the SPA can authenticate via `POST /api/auth/login` → `pergen_session` cookie + `X-CSRF-Token`. The legacy `X-API-Token` header path keeps working unchanged. | Wave-6 Phase F |
| **`PERGEN_SESSION_LIFETIME_HOURS`** | **`8`** | Maximum lifetime of a `pergen_session` cookie (was Flask's 31-day default). | **Wave-7 H-2** |
| **`PERGEN_SESSION_IDLE_HOURS`** | = lifetime | Idle-timeout threshold. Cookie-auth branch clears the session on overflow. | **Wave-7 H-2** |
| **`PERGEN_TRUST_PROXY`** | unset | When `=1`, mounts `werkzeug.middleware.proxy_fix.ProxyFix(x_for=1, x_proto=1, x_host=1)`. **Required behind nginx / Caddy / cloud LB**; do NOT set on un-proxied deployments. | **Wave-7 H-1** |
| **`PERGEN_DEV_BIND_HOST`** | **`127.0.0.1`** | Bind host for the legacy `python -m backend.app __main__` entry point. | **Wave-7 H-3** |
| **`PERGEN_DEV_ALLOW_PUBLIC_BIND`** | unset | Override for the bind-host guard. Required only for `python -m backend.app`; production should always boot via `FLASK_APP=backend.app_factory:create_app`. | **Wave-7 H-3** |
| `PERGEN_REQUIRE_DESTRUCTIVE_CONFIRM` | unset (dev) / always-on (prod) | `/api/transceiver/recover` and `/api/transceiver/clear-counters` require `X-Confirm-Destructive: yes`. | C-4 |
| `PERGEN_BLOCK_INTERNAL_PING` | unset | **Wave-7.1 (2026-04-23) deliberate posture change.** `/api/ping` now defaults to **allow** internal targets (RFC1918 / loopback / link-local / multicast / reserved) because Pergen is operated against the operator's own management network. Set `=1` to re-enable the audit-H3 default-deny SSRF guard for an internet-exposed deployment. The legacy `PERGEN_ALLOW_INTERNAL_PING=1` is honoured as a no-op (allow is the default); if BOTH are set, BLOCK wins. | H-3 (relaxed) |
| `PERGEN_DEV_OPEN_API` | unset | When `=1`, dev/test boot with no token gate is allowed. Without it, a missing `PERGEN_API_TOKEN(S)` in development is a hard error. | Audit wave-2 H-05 |
| `PERGEN_SSH_STRICT_HOST_KEY` / `PERGEN_SSH_KNOWN_HOSTS` | unset / unset | **Default `AutoAddPolicy` is intentional** for an internal-only Pergen deployment — it lets paramiko TOFU the host key on first contact so new leaves / spines auto-enroll. Set `=1` (paired with `PERGEN_SSH_KNOWN_HOSTS=<path>`) to lock the runner down to Paramiko `RejectPolicy` for an untrusted-network deployment. **Wave-7.1**: the AutoAdd notice now fires once per process at module-import (level INFO), not WARN-per-call — multi-device runs no longer drown the audit log. | H1-ssh (intentional default) |
| **`PERGEN_RECOVERY_BOUNCE_DELAY_SEC`** | **`5`** | **Wave-7.3 (2026-04-23) bug fix.** Delay (in seconds) between the `shutdown` and `no shutdown` stanzas of an interface bounce in `/api/transceiver/recover`. Each interface now executes as TWO separate SSH/eAPI sessions per bounce (was one combined script that NX-OS coalesced asynchronously, leaving ports stuck errdisabled). Sequential per-interface; clamped to `[1, 30]` seconds; default 5 matches the operator-validated CLI workflow. Strict allowlist enforces that only `configure terminal` / `configure` / `interface <validated>` / `shutdown` / `no shutdown` / `end` ever leave this code path. | **Wave-7.3** |

## Pergen credential store — wave-7 v2 fall-through bridge

**This is the single most important context item for any Pergen task
that touches credentials, runners, or device-exec routes.**

The credential **write path** is unambiguous:
`POST /api/credentials` → `CredentialService` → `CredentialRepository`
→ `EncryptionService` → `instance/credentials_v2.db`
(PBKDF2 600k + AES-128-CBC + HMAC-SHA256).

The credential **read path** has a two-tier fall-through (since wave-7,
2026-04-23):

```
                    legacy callers (5 blueprints + runner.py +
                                    find_leaf + nat_lookup)
                                              │
                                              ▼
                          credential_store.get_credential()
                                              │
                          ┌───────────────────┴────────────────────┐
                          ▼                                        ▼
              instance/credentials.db                       row missing?
              (legacy SHA-256 → Fernet)                            │
                          │ row found? → return                    ▼
                                                      _read_from_v2(name, secret_key)
                                                      instance/credentials_v2.db
                                                      (PBKDF2 600k → AES-CBC+HMAC)
                                                                   │
                                                          row found? → return
                                                          row missing or
                                                          decrypt fails? → return None
```

What this means for an agent writing or reviewing Pergen code:

- **Do not assume `credential_store.get_credential()` is "legacy-only".**
  Since wave-7 it transparently bridges to the v2 store, so a credential
  added through the new HTTP CRUD on a fresh install **is** reachable
  from every device-exec route. The bridge fires only when the legacy
  DB has no row — operators with rows in `instance/credentials.db` see
  no behavioural change.
- **Do not refactor away `_v2_db_path()` or `_read_from_v2()` in
  `backend/credential_store.py`** without first migrating all 6 legacy
  consumers off the legacy module. The bridge is a transition aid for
  the still-pending Phase 5 / Phase 6 of
  `docs/refactor/DONE_credential_store_migration.md`. Removing the
  bridge before those phases lands re-introduces the fresh-install break
  that motivated wave-7 C-1 / H-4.
- **Use `CredentialService` for any new code path that writes or reads
  credentials.** The legacy module exists only because of the in-flight
  migration; new consumers should pull from
  `current_app.extensions["credential_service"]` and bypass the legacy
  module entirely.
- **The migration script remains the canonical operator action** when
  the legacy DB has data that needs the stronger PBKDF2 KDF. The bridge
  is best-effort (failures swallowed); the script is durable
  (idempotent + verify step + non-destructive). Operator-facing
  documentation of the script:
  [`HOWTOUSE.md`](./HOWTOUSE.md) §8.

Pinned by `tests/test_security_credential_v2_fallthrough.py` (6 tests).
Full discussion:
[`docs/refactor/DONE_credential_store_migration.md`](./docs/refactor/DONE_credential_store_migration.md)
"Wave-7 update" section.

## Latest audit references (start here when investigating a regression)

- [`docs/security/DONE_audit_2026-04-23-wave7.md`](./docs/security/DONE_audit_2026-04-23-wave7.md) — wave-7 security audit (current).
- [`docs/code-review/DONE_python_review_2026-04-23-wave7.md`](./docs/code-review/DONE_python_review_2026-04-23-wave7.md) — wave-7 Python review.
- [`docs/test-coverage/DONE_coverage_audit_2026-04-23-wave7.md`](./docs/test-coverage/DONE_coverage_audit_2026-04-23-wave7.md) — current coverage by module.
- [`docs/test-coverage/DONE_e2e_gap_analysis_2026-04-23-wave7.md`](./docs/test-coverage/DONE_e2e_gap_analysis_2026-04-23-wave7.md) — Playwright suite stability.
- [`patch_notes.md`](./patch_notes.md) v0.7.1 — wave-7 entry at the top.
- All `docs/refactor/DONE_*` plans — completed; carry historical context.
