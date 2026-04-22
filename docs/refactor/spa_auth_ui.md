# SPA ↔ Token-Gate Auth UI Gap — Implementation Plan

> **Status:** PLAN ONLY — no code changes proposed in this document.
> **Owner area:** `backend/app_factory.py::_install_api_token_gate` ↔ `backend/static/{index.html, js/app.js}`
> **Related deferred items:** *Token-gate immutability* (parse `PERGEN_API_TOKEN(S)` once at `create_app`), *CSP/HSTS on JSON*, *Audit-log coverage*.
> **Scope:** Close the gap where the SPA cannot acquire an `X-API-Token` without an operator pasting one, while keeping the existing per-actor token model intact.

---

## 1. Requirements Restatement

The token gate (`backend/app_factory.py:163-266`) requires every `/api/*` request to carry an `X-API-Token` header that matches one of the configured per-actor tokens. In production this is **fail-closed**: `create_app` refuses to boot without `PERGEN_API_TOKEN(S)`. The SPA shipped at `backend/static/index.html` + `backend/static/js/app.js` issues **73 `fetch(...)` calls** (grep summary in §2.2) and **none of them set `X-API-Token`**. Today the SPA only works in three modes:

1. **Dev/test** with the token gate disabled (no env vars set; gate logs a one-shot WARN and serves the API openly).
2. **Production behind something** that injects the header for the operator (no such "something" exists in this repo today — no Dockerfile, no nginx/Caddy/compose file under the repo root or `docs/`).
3. **An operator manually pasting a token into a hand-crafted `curl`/Postman call** — which defeats the SPA entirely.

The required end-state:

| ID | Requirement | Source of truth |
|----|-------------|-----------------|
| R1 | Operator can authenticate **once per session** in the browser without ever seeing the raw token. | New |
| R2 | Every `/api/*` call from the SPA carries a credential the gate accepts. | `_install_api_token_gate` |
| R3 | Per-actor accountability is preserved (`flask.g.actor` populated correctly so audit lines stay attributable). | `app_factory.py:262`, `request_logging.py` |
| R4 | Production refuses to start with an open posture (the existing fail-closed contract is unchanged). | `app_factory.py:220-235` |
| R5 | No new long-term secret leaks into `localStorage` / log lines / proxy access logs. | `logging_config.py:39-44` already redacts `cookie` / `set-cookie`. |
| R6 | The exempt path set (`/api/health`, `/api/v2/health`, `/`) keeps working unauthenticated for liveness probes and SPA bootstrap. | `app_factory.py:199` |
| R7 | Dev mode (no tokens configured) keeps booting with a WARN — no new mandatory dependency for local hacking. | `app_factory.py:240-249` |
| R8 | E2E Playwright suite (`tests/e2e/specs/*`) keeps passing, with at most one new "log in" page object. | `playwright.config.ts` |

**Non-goals (explicit):**
- Multi-tenant user management, password reset flows, MFA, per-route RBAC, OAuth federation. Pergen's auth model today is a small set of named operator tokens; we are closing the UI gap on top of that, not redesigning identity.
- Replacing the device-credential page (`#credential` route in `index.html:633`) — that store handles **device** credentials, not app login.

---

## 2. Current State Analysis

### 2.1 Token gate (server side)

- **File:** `backend/app_factory.py`
- **Function:** `_install_api_token_gate(app)` — `app_factory.py:163-266`
- **How it gates:** `before_request` hook (`app_factory.py:237-264`) reads `request.headers.get("X-API-Token", "")` and `hmac.compare_digest`'s it against every configured `(actor, token)` pair. Match → `g.actor = matched_actor`; miss → `401 {"error": "missing or invalid X-API-Token header"}`.
- **Token sources** (re-read every request, see deferred *Token-gate immutability* item):
  - `PERGEN_API_TOKENS=actor1:tok1,actor2:tok2` (preferred, per-actor)
  - `PERGEN_API_TOKEN=<random>` (legacy, sets `g.actor = "shared"`)
- **Production fail-closed:** `app_factory.py:219-235` raises at `create_app` time if no tokens or any token < 32 chars.
- **Exempt set:** `{"/api/health", "/api/v2/health", "/"}` — `app_factory.py:199`.
- **Other security middleware already in place:** response headers (`X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`) per `HOWTOUSE.md:364-371`; CSP set on HTML responses per `tests/test_security_html_responses_include_csp.py`. **CSRF is NOT enabled** — there is no `Flask-WTF`/`CSRFProtect` import anywhere in `backend/`.

### 2.2 SPA (client side)

- **Entry HTML:** `backend/static/index.html` (1,351 lines) — single-page app, all panels in-document, no `<script type="module">`, no auth UI of any kind. The string `login` appears 9× and **all 9 are about device credentials or button tooltips**, not user-to-app auth (`index.html:569,633,826,832,835,1004,1272,1279,1331`).
- **Entry JS:** `backend/static/js/app.js` (5,253 lines).
- **`fetch()` audit:** 73 call sites; representative examples:
  - `app.js:485` `fetch(API + "/api/ping", { method: "POST", headers: { "Content-Type": "application/json" }, body: ... })`
  - `app.js:266` `fetch(API + path)` — bare GET
  - `app.js:3870` `fetch(API + "/api/inventory/device?hostname=...", { method: "DELETE" })`
  - `app.js:5239` `fetch(API + "/api/credentials", { method: "POST", headers: { "Content-Type": "application/json" }, body: ... })`
- **Search for token:** `grep -nE 'X-API-Token|apiToken|api_token'` against `app.js` returns **zero** matches. The string `token` only appears inside `localStorage` keys for unrelated SPA state (`pergen_last_pre`, `bgpPrefillPrefix`, etc., `app.js:1297, 2175, 2247, 2264, 3072, …`).
- **Authorization header:** never set anywhere. There is no global `fetch` wrapper today.
- **Conclusion:** the SPA was written assuming the gate is OFF or a proxy injects the header upstream. Neither assumption holds in any in-repo prod boot path.

### 2.3 Session / cookie / login infrastructure

- **`SECRET_KEY`** is wired and validated for production (`config/app_config.py:114`, `:177-202`; `app_factory.py:135`, `:380`, `:406`). So **Flask's signed-cookie `session` is available out of the box** — no new dependency required to issue an HttpOnly auth cookie.
- **`Flask-Login` / `flask_login`:** not present (grep of `backend/` returns zero matches).
- **CSRF:** not enabled. `request_logging.py:21` only mentions CSRF in a comment about what *not* to log.
- **`/login` route:** does not exist. Greppable confirmation: no blueprint registers it (`app_factory.py:271-301` lists all 12 blueprints; none is auth/login).

### 2.4 Reverse proxy / deployment surface

- **No `Dockerfile`, no `docker-compose*`, no `nginx.conf`, no `Caddyfile`, no `*.conf` anywhere outside `node_modules/venv/vendor_pkgs`.** The single deployment instruction (`HOWTOUSE.md:142-153`) is a bare `gunicorn -w 4 -b 0.0.0.0:8000 'backend.app_factory:create_app("production")'`. That means *the codebase ships zero opinion about a fronting proxy today.*
- `HOWTOUSE.md:368-371` does acknowledge a possible reverse proxy but only in the context of header overrides.
- `run.sh` boots Flask's dev server bound to `127.0.0.1:5000`.

### 2.5 Related in-flight test scaffolding

- `tests/test_security_token_gate_immutable.py` — **xfail** today. Wants tokens parsed once at `create_app` instead of every request (the *Token-gate immutability* deferred item). Any plan here must **not regress** the path that test will eventually cover.
- `tests/test_security_token_gate_parsing.py` — green; covers the actor parsing in `_parse_actor_tokens`.

---

## 3. Architectural Options

Each option assumes R1–R8 must hold. Each is described as a complete delivery, not a partial step.

### Option A — Reverse-proxy auth header injection

A small fronting proxy (Caddy, nginx, or Traefik) terminates TLS, performs operator authentication (basic auth, OIDC, mTLS — proxy's choice), and sets `X-API-Token: <per-actor-token>` on every upstream request to gunicorn. The Flask app is bound to `127.0.0.1` only and refuses requests that don't carry a valid token (the gate is unchanged). The SPA is also unchanged.

**What ships in the repo:**
- A reference `deploy/Caddyfile` (or `deploy/nginx.conf`) committed under `docs/deploy/`.
- A new section in `HOWTOUSE.md` and `ARCHITECTURE.md` declaring "Pergen MUST be fronted by an authenticating proxy in production."
- A startup check (optional) in `_install_api_token_gate` that warns when `request.headers.get("X-Forwarded-For")` is empty in production — i.e., looks like Pergen is exposed directly.

**Pros:**
- Zero SPA churn; zero new server code in Pergen.
- Reuses battle-tested auth implementations; auth choice is deferred to ops.
- Per-actor accountability via proxy mapping `proxy-user → token`.

**Cons:**
- The header `X-API-Token` is **trivially spoofable** if the proxy isn't actually in front. If anyone ever bypasses the proxy (port misconfig, dev container leaked to a network), the API is open to anyone who knows the token format. We have no in-app proof the request really came through the proxy.
- Pushes a hard ops dependency onto every deploy — including small/internal ones that today just run `run.sh`.
- Doesn't help local dev with a token gate enabled (you'd need to also run a local proxy).
- We commit zero auth UX to the repo; the user experience varies wildly per deploy.

### Option B — In-app login page → HttpOnly cookie session

A new `auth_bp` blueprint adds:

- `GET /login` → small HTML form (or SPA route) asking for an actor name + token (or username+password hashed against an env-supplied table that maps to actor tokens).
- `POST /api/auth/login` → validates credentials in constant time, sets a Flask signed-session cookie containing `{"actor": "<actor>", "iat": ..., "csrf": "<token>"}`. **No raw API token in the cookie.**
- `POST /api/auth/logout` → clears session.
- `GET /api/auth/whoami` → returns `{"actor": "<actor>"}` for the SPA to render an "Logged in as X — Logout" affordance.

The token gate (`_enforce_api_token`) is updated to accept **either**:
1. The existing `X-API-Token` header (machine clients, CI, curl), OR
2. A valid signed session cookie carrying an actor that resolves to a configured token, AND a matching `X-CSRF-Token` header for unsafe methods (POST/PUT/DELETE).

The SPA installs a single `pergenFetch(path, opts)` wrapper that:
- Adds `X-CSRF-Token` from a meta tag for unsafe methods.
- On `401`, redirects to `/login?next=<current-hash>`.

Cookie attributes: `HttpOnly; Secure; SameSite=Lax; Path=/`.

**Pros:**
- Self-contained — no required external infra. `run.sh` keeps working.
- Defense-in-depth: even if the token leaks, an attacker still needs the cookie+CSRF pair from a logged-in browser.
- Token never enters the DOM, never enters `localStorage`, never enters a URL query string, never enters proxy access logs (cookies are already in the redaction set, `logging_config.py:43`).
- Per-actor accountability preserved (cookie carries actor, gate sets `g.actor`).
- Backwards compatible with existing `X-API-Token` for CI / `curl`.

**Cons:**
- New attack surface in Pergen itself: login throttling, CSRF correctness, cookie-handling bugs, session fixation, signed-cookie key rotation.
- Requires a small templating decision (Jinja `login.html` vs SPA-served `/login` hash route).
- Forces the *Token-gate immutability* deferred work to happen first — or in the same PR — because the gate now has two acceptance paths and re-reading env on every request becomes a worse smell.
- Local dev with the gate ON still requires an operator to log in once per browser; not as zero-friction as Option A behind a transparent proxy.

### Option C — OIDC / OAuth delegation (Authentik, Authelia, Keycloak, Cloudflare Access, etc.)

Pergen exposes itself behind an OIDC-aware proxy or in-process OIDC client. Operators sign in to the IdP; the proxy or middleware validates the JWT/cookie and either (a) translates the IdP identity to a configured actor token (proxy-injected `X-API-Token`, like Option A but with real auth), or (b) Pergen itself validates the JWT and uses a `sub → actor` map.

**Pros:**
- Best identity story: real users, real sessions, MFA, group claims, central revocation.
- Eliminates per-actor static tokens in the long run.
- Audit trail is much richer (`g.actor` becomes the IdP `sub` / `preferred_username`).

**Cons:**
- **Massive scope creep** for a tool whose entire identity model today is "a string in an env var." Adds a hard dependency on external infra (an IdP) for every deployment.
- Requires picking an IdP or shipping a generic OIDC client + config — both are a new long-term maintenance surface.
- Still needs Option A or B underneath for machine clients (CI, scripts).
- Doesn't fit the spirit of "close the SPA gap"; it's a re-platforming.

### 3.1 Pros/Cons matrix

| Dimension | A — Proxy injection | B — In-app login + cookie | C — OIDC delegation |
|---|---|---|---|
| **In-repo code change** | Tiny (docs + warn) | Medium (~ 1 blueprint, 1 fetch wrapper, ~6 tests) | Large (client lib + config + tests) or Tiny (if all in proxy) |
| **New runtime dependencies** | Caddy/nginx in prod | None | IdP + OIDC lib |
| **Local dev friction (gate ON)** | High (need local proxy) | Low (one login per browser) | Very high (need local IdP) |
| **Per-actor accountability** | Yes, via proxy mapping | Yes, via session `actor` | Yes, via IdP `sub` |
| **Header-spoofing exposure** | **HIGH** if proxy bypassed | None (cookie is signed) | None (JWT signature) |
| **CSRF surface added** | None | **Yes — must implement** | Depends on transport |
| **Affects deferred *immutability* item** | No | Yes — should land together | Yes |
| **SPA churn** | None | Single `pergenFetch` wrapper + `/login` route | Same as B + token refresh |
| **Reversible if we change our mind** | Easily | Easily (gate keeps `X-API-Token` path) | Hard — IdP coupling sticks |
| **Time-to-merge estimate** | 1-2 days | 4-6 days | 2-3 weeks minimum |

---

## 4. Council Verdict

The decision is genuinely ambiguous: A is the cheapest, B is the most self-contained, C is the most "correct" identity story but enormously over-scoped. Convening the council per the `council` skill.

**Architect (initial in-context position, formed before reading other voices):**
B — In-app login → HttpOnly cookie session.
Why: Pergen ships as a self-contained Flask app today (`run.sh`, single `gunicorn` line). The fail-closed production posture in `app_factory.py:219-235` is a strong promise that *Pergen itself* refuses to be open. Outsourcing auth to a proxy weakens that promise to "Pergen is open if you forget to deploy the proxy." Closing the gap inside the app keeps the security property local and verifiable.
Risk: CSRF and cookie handling are new attack surface we haven't proven we can ship correctly.

**Skeptic:**
Position: Challenge the framing. Why does the SPA need to authenticate at all? Pergen is an internal network-ops tool — every real deployment is already on a private VLAN/VPN/jump host. The "right" answer is often "deploy it behind tailscale/wireguard/zero-trust mesh and document that the token gate is the *second* layer, not the first."
Reasoning: (a) The `gunicorn -b 0.0.0.0:8000` line in `HOWTOUSE.md:149` is what's actually scary, not the missing login page. (b) Adding an in-app login implies Pergen is internet-facing, which it almost certainly should never be. (c) Every line of auth code we add is a line we have to keep secure forever.
Risk: We might ship Option B and operators interpret it as "now safe to expose to the public internet." That's worse than today.
Surprise the others may miss: the `_enforce_api_token` re-reads env *every request* (`app_factory.py:239`) — there's a quiet timing-attack and ops surprise here that none of A/B/C addresses by itself.

**Pragmatist:**
Position: Option A, shipped now with a strong "proxy is mandatory" warning at boot, then revisit B in a later PR if real users complain.
Reasoning: (a) Today, with the gate ON, the SPA is **broken**. Fixing that with a `Caddyfile` and 5 lines of docs unblocks every operator this week. (b) Option B is correct but takes 4-6 days and forces the immutability work into the same PR. (c) The header-spoofing risk is real but manageable: bind gunicorn to 127.0.0.1 in the documented prod recipe and the spoofing surface goes to zero.
Risk: We ship A, then nobody ever revisits B because "it works," and we live with a fragile contract forever.
Surprise: the existing E2E suite (`tests/e2e/specs/*`) runs against `./run.sh` which has the gate OFF. Whichever option ships, the E2E suite has to pick one mode or run both. That's a real cost neither A nor B has accounted for above.

**Critic:**
Position: B, but only if delivered with CSRF tests as RED-first. Otherwise A.
Reasoning: (a) Cookie-based auth without CSRF is strictly worse than today's "no SPA auth at all" — at least today there's no ambient credential to ride. (b) Session fixation (cookie set before login completes) is the textbook bug we will ship if we're not careful. (c) Logging `Set-Cookie` is already redacted (`logging_config.py:43`) — good — but error responses that 500 with stack traces could leak the signed cookie value if we're sloppy in `request_logging.py`.
Risk: A naïve B implementation introduces a CSRF bug across 73 fetch sites because the SPA has no central wrapper today; one missed call site = one CSRF-able endpoint.
Surprise: The SPA has `73 fetch() call sites` and **zero of them** currently go through a wrapper. Wrapping them is itself a refactor that changes blast radius far beyond "add a login page."

### Verdict

- **Consensus:** All four agree the *status quo is broken under the gate* and shipping nothing is not an option.
- **Strongest dissent:** Skeptic challenges the premise — argues the right answer is "network-layer auth (VPN/zero-trust) + keep the gate as defense-in-depth + document loudly," not adding app-layer login at all. The Critic seconds this insofar as a sloppy B is worse than A.
- **Premise check:** Yes, valid. Pergen is an internal tool; we should not pretend it is hardening for hostile-internet exposure.
- **Recommendation:** **Ship Option B (in-app login → HttpOnly cookie session) — but stage it as a 4-phase TDD delivery that lands the SPA `pergenFetch` wrapper *first*, then CSRF, then the login page, then docs that explicitly state "the gate is the second layer; deploy behind a private network."** Keep `X-API-Token` accepted for machine clients so Option A remains a *valid additional* layer for operators who want it.

Rationale for picking B over A despite the Pragmatist preferring A:
1. **Fail-closed locality.** The `app_factory.py:223` promise ("refusing to start with an open API") is an in-app guarantee. Option A moves part of that guarantee to a config file in a different repo, which we cannot test in CI. Option B keeps the guarantee inside the app.
2. **Header-spoofing is a real failure mode** (Critic + Architect agree). Once you accept `X-API-Token` from any caller, a misrouted port = open API. A signed-cookie path closes that even when the token leaks.
3. **A is not foreclosed by B.** The gate keeps `X-API-Token` as the machine path. Operators who *want* a fronting proxy can still deploy one — they just no longer *have to.*
4. **Skeptic's "deploy behind a VPN" point is correct and survives in B** as the new docs section, not as an excuse to ship nothing.

---

## 5. Recommendation

**Adopt Option B with the four staging constraints from the verdict:**

1. Land `pergenFetch` SPA wrapper and convert all 73 call sites **before** any auth changes are merged. This is a no-behavior-change refactor that makes auth changes safe.
2. Land CSRF infrastructure (token issued in cookie + meta tag, validated on unsafe methods) **before** the login page.
3. Land the login page + cookie session, with the gate accepting **either** cookie-with-CSRF **or** legacy `X-API-Token`.
4. Land docs (`HOWTOUSE.md`, `ARCHITECTURE.md`, new `docs/deploy/auth.md`) that state the layered model: network → gate → cookie session.

Co-deliver the deferred *Token-gate immutability* item in Phase 3 (when we touch `_install_api_token_gate` for the cookie path, parse-once-at-create_app drops out for free).

---

## 6. Implementation Phases (TDD-first)

> Each phase is a standalone PR. Each step lists the **failing test first**, then the implementation, then the verification.

### Phase 0 — Fixture & decision lock-in (~0.5 day)

| # | Step | File(s) | Risk |
|---|------|---------|------|
| 0.1 | Write ADR-style note at top of this doc confirming Option B chosen. | `docs/refactor/spa_auth_ui.md` | Low |
| 0.2 | Add a Playwright fixture that runs `./run.sh` with **the gate enabled** (`PERGEN_API_TOKENS=ci:` + 32-char token). Today's E2E runs with the gate OFF. | `playwright.config.ts`, `tests/e2e/fixtures/auth.ts` (new) | Low |
| 0.3 | Mark all current E2E specs `test.skip` under the gated fixture (they will go green again in Phase 3). Keep them green under the open fixture. | `tests/e2e/specs/*.spec.ts` | Low |

### Phase 1 — `pergenFetch` SPA wrapper, no behavior change (~1 day)

> Goal: every API call goes through one place, so Phase 2/3 can change auth in one spot.

| # | Step | File(s) | Risk |
|---|------|---------|------|
| 1.1 | RED: new `tests/test_spa_fetch_wrapper.py` (or jsdom test under `tests/e2e/unit/`) asserts that `app.js` exposes `window.pergenFetch` and that no `fetch(API + ...)` call survives outside the wrapper. Use a static grep test (Python `ast`-style `re.findall(r'\bfetch\(\s*API\b', source)`) — must return 1 match (the wrapper itself). | `tests/test_spa_fetch_wrapper.py` (new) | Low |
| 1.2 | GREEN: introduce `pergenFetch(path, opts={})` near top of `app.js`. Replaces every `fetch(API + ...)` call. **No header changes yet** — pure passthrough. | `backend/static/js/app.js` (73 call sites → 1 wrapper) | Medium (mechanical but wide blast radius) |
| 1.3 | REGRESSION: full Playwright suite + manual smoke under the OPEN fixture. Must be byte-identical request stream. | n/a | Medium |
| 1.4 | REVIEW: invoke `code-reviewer` agent — explicit instruction to look for missed call sites and shadowed `fetch` references. | n/a | Low |

### Phase 2 — CSRF infrastructure (server + wrapper), gate untouched (~1 day)

| # | Step | File(s) | Risk |
|---|------|---------|------|
| 2.1 | RED: `tests/test_security_csrf_required.py` (new) — for every POST/PUT/DELETE in the route map, assert that a request **without** `X-CSRF-Token` returns 403 when the cookie session path is later enabled, and that requests via `X-API-Token` are exempt. Initial form: parametrize over `app.url_map.iter_rules()` and `xfail` until Phase 3 ships. | `tests/test_security_csrf_required.py` (new) | Low |
| 2.2 | GREEN (partial): add `backend/security/csrf.py` — pure-function `issue_csrf()` (returns a 32-byte URL-safe token) + `verify_csrf(supplied, expected)` (constant-time). Unit-test in `tests/test_security_csrf_unit.py`. | `backend/security/csrf.py` (new) | Low |
| 2.3 | GREEN: extend `pergenFetch` to read CSRF from `<meta name="pergen-csrf" content="...">` and inject `X-CSRF-Token` for unsafe methods. **Does nothing useful yet** — server doesn't verify until Phase 3. Wrapped so Phase 3 is a one-line server change. | `backend/static/js/app.js`, `backend/static/index.html` (meta tag, value still empty) | Low |
| 2.4 | REGRESSION: Playwright OPEN fixture stays green (CSRF is currently unenforced). | n/a | Low |

### Phase 3 — `auth_bp`, cookie session, gate accepts both paths, **immutability fix co-landed** (~2 days)

| # | Step | File(s) | Risk |
|---|------|---------|------|
| 3.1 | RED: `tests/test_security_token_gate_immutable.py` — flip from `xfail` to required-pass. Asserts `_install_api_token_gate` parses tokens **once** in `create_app` and reads from a frozen mapping inside `_enforce_api_token`. | `tests/test_security_token_gate_immutable.py` (existing, un-xfail) | Low |
| 3.2 | RED: `tests/test_auth_login_flow.py` (new) covers: (a) `POST /api/auth/login` with bad creds → 401 + constant-time delay (`time.monotonic` budget assertion); (b) good creds → `Set-Cookie: session=...; HttpOnly; Secure; SameSite=Lax` + JSON body `{"actor": "..."}`; (c) subsequent `/api/inventory` with cookie+CSRF → 200; (d) cookie without CSRF on POST → 403; (e) `POST /api/auth/logout` → 204 + `Set-Cookie` clearing session. | `tests/test_auth_login_flow.py` (new) | Low |
| 3.3 | RED: `tests/test_auth_session_fixation.py` (new) — cookie value pre-login MUST NOT equal cookie value post-login. | `tests/test_auth_session_fixation.py` (new) | Low |
| 3.4 | RED: `tests/test_auth_actor_pinning.py` (new) — `g.actor` after cookie auth equals the actor selected at login; audit log line carries it (matches the existing pattern in `request_logging.py`). | `tests/test_auth_actor_pinning.py` (new) | Low |
| 3.5 | RED: flip the `xfail`s in `tests/test_security_csrf_required.py` to required-pass. | existing | Low |
| 3.6 | GREEN: new `backend/blueprints/auth_bp.py` (~120 lines): `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/whoami`, `GET /login` (Jinja-rendered minimal HTML form with CSRF meta). Uses `flask.session` (signed cookie via existing `SECRET_KEY`). Login validates submitted token against the parsed-once token map; sets `session["actor"]` and `session["csrf"]`. | `backend/blueprints/auth_bp.py` (new), `backend/blueprints/__init__.py` | Medium |
| 3.7 | GREEN: refactor `_install_api_token_gate` (`app_factory.py:163-266`): parse tokens once at `create_app`, store frozen `MappingProxyType` on `app.extensions["pergen"]["actor_tokens"]`. `_enforce_api_token` accepts either `X-API-Token` (legacy/CI) **or** signed-session-with-actor + matching `X-CSRF-Token` for unsafe methods. Exempt set unchanged. | `backend/app_factory.py` | Medium-High |
| 3.8 | GREEN: register `auth_bp` in `_register_blueprints` (`app_factory.py:269-301`). | `backend/app_factory.py` | Low |
| 3.9 | GREEN: `pergenFetch` — on 401 response, navigate to `/login?next=<location.hash>`. | `backend/static/js/app.js` | Low |
| 3.10 | GREEN: Phase-0 Playwright specs un-skipped under the GATED fixture; add one new spec `tests/e2e/specs/auth_login.spec.ts` (login → land on dashboard → logout → redirected to /login). | `tests/e2e/specs/auth_login.spec.ts` (new) | Low |
| 3.11 | REVIEW: invoke `security-reviewer` agent on the diff. Required checks: cookie attrs, CSRF correctness, constant-time login, no token in logs, session fixation. | n/a | Medium |

### Phase 4 — Login throttling, observability, docs (~0.5 day)

| # | Step | File(s) | Risk |
|---|------|---------|------|
| 4.1 | RED: `tests/test_auth_login_throttling.py` — 10 failed logins from same IP within 60s → next attempt 429 with `Retry-After`. | `tests/test_auth_login_throttling.py` (new) | Low |
| 4.2 | GREEN: in-process token-bucket per `(remote_addr, username)` in `auth_bp`. No Redis; small dict + lock keyed by IP, TTL-pruned. | `backend/blueprints/auth_bp.py` | Low |
| 4.3 | OBSERVABILITY: emit `app.audit` lines for `auth.login.success`, `auth.login.fail`, `auth.logout`, `auth.csrf.mismatch` matching the format used elsewhere; co-deliver an entry in the deferred *Audit-log coverage* table. | `backend/blueprints/auth_bp.py`, `backend/logging_config.py` (no change expected — already redacts `cookie`) | Low |
| 4.4 | DOCS: update `HOWTOUSE.md §4.4` with: "Pergen now ships an in-app login at `/login`. The gate accepts cookie+CSRF for browsers and `X-API-Token` for machine clients. **Pergen still expects to run on a private network**; the in-app login is the second layer, not the first." Add `docs/deploy/auth.md` describing both modes (cookie + machine token) and the optional Option-A fronting proxy with sample Caddyfile. Update `ARCHITECTURE.md` token-gate section. | docs only | Low |
| 4.5 | DOCS: add a paragraph to `patch_notes.md` "Deferred work" table marking the *SPA-vs-token-gate* row CLOSED and the *Token-gate immutability* row CLOSED. | `patch_notes.md` | Low |

---

## 7. Dependencies

| Dependency | Where | Why |
|---|---|---|
| Existing `SECRET_KEY` validation in `ProductionConfig` (`config/app_config.py:177-202`) | Already in tree | Required for signed-cookie sessions to be safe in prod. **No new dep.** |
| Existing `_install_api_token_gate` (`app_factory.py:163-266`) | Already in tree | Phase 3 modifies in place. |
| Existing `pergen_ext = app.extensions.setdefault("pergen", ...)` slot (`app_factory.py:195`) | Already in tree | Frozen token map will live here. |
| Existing log redaction of `cookie` / `set-cookie` (`logging_config.py:43`) | Already in tree | R5 satisfied. |
| Deferred *Token-gate immutability* item | `tests/test_security_token_gate_immutable.py` (xfail) | Co-landed in Phase 3. |
| Playwright runner + `./run.sh` boot (`playwright.config.ts`) | Already in tree | Gated fixture added in Phase 0. |
| **No new Python packages.** Flask sessions, `hmac.compare_digest`, `secrets.token_urlsafe`, `MappingProxyType` are stdlib/already-imported. | n/a | Lowers maintenance cost. |

**Explicitly NOT required:** `Flask-WTF`, `Flask-Login`, `itsdangerous` (Flask already bundles it), Redis, an IdP, a reverse proxy.

---

## 8. Risks

### HIGH

- **R-H1: CSRF gap during the staged rollout.** Phase 2 adds the `X-CSRF-Token` header but the server doesn't verify until Phase 3. If Phase 2 is shipped to prod alone (out-of-order merge), the SPA looks like it's protected when it isn't.
  - *Mitigation:* explicitly mark Phase 2's PR as "DO NOT DEPLOY ALONE — paired with Phase 3"; add a feature flag `PERGEN_AUTH_COOKIE_ENABLED=false` default that gates the cookie path. Phase 3 flips the default.
- **R-H2: Missed `fetch` call sites in Phase 1.** With 73 sites, one missed conversion = one endpoint that bypasses CSRF in Phase 3.
  - *Mitigation:* Step 1.1's static grep test is mandatory and runs in CI. Plus `code-reviewer` agent pass.
- **R-H3: Session fixation.** If `flask.session` is populated with anything before login completes (e.g., a CSRF token issued to anonymous users that survives login), an attacker can pre-set a victim's session.
  - *Mitigation:* Test 3.3 enforces `session.regenerate()`-equivalent on login (in Flask, that's `session.clear()` then re-populate before `Set-Cookie` is written). Code review checklist item.

### MEDIUM

- **R-M1: Header spoofing if `X-API-Token` accepted alongside cookie.** A misconfigured load balancer could allow `X-API-Token` from a network where it shouldn't appear.
  - *Mitigation:* Optional Phase 4.6 — boot warning when `_resolve_actor_tokens()` returns >0 entries AND `request.remote_addr` is publicly routable AND `X-Forwarded-For` is empty. Logged at WARN once, not enforced.
- **R-M2: Login throttling memory leak.** In-process dict grows unbounded if every IP gets an entry.
  - *Mitigation:* Test 4.1 includes a "100 distinct IPs → dict size capped at 1024 with LRU eviction" assertion.
- **R-M3: Cookie set without `Secure` in dev.** If we hardcode `Secure`, dev (`http://127.0.0.1:5000`) never gets the cookie back.
  - *Mitigation:* `Secure` flag pulled from `app.config["SESSION_COOKIE_SECURE"]` which defaults `True` in `ProductionConfig` and `False` in `DevelopmentConfig`. Add explicit test.
- **R-M4: E2E suite dual-mode runtime cost.** Running every spec under both OPEN and GATED fixtures roughly doubles CI time.
  - *Mitigation:* Default CI matrix = GATED only after Phase 3 lands; OPEN fixture kept as a tagged subset (`@open`) for the dev-mode regression.

### LOW

- **R-L1: Operator confusion** ("do I need to log in or use a token?"). Resolved by docs (Phase 4.4) and a clear `whoami` indicator in the SPA header.
- **R-L2: Cookie domain/path scoping** for installs that mount Pergen under a sub-path. Use `Path=/`; document as a known limitation.
- **R-L3: SECRET_KEY rotation** invalidates all sessions. Acceptable; document as expected behavior.
- **R-L4: Login page CSP.** The new `/login` HTML must meet the same CSP that `tests/test_security_html_responses_include_csp.py` enforces. Add a paired test.

---

## 9. Estimated Complexity

| Phase | Effort | Risk profile |
|---|---|---|
| Phase 0 — fixture + lock-in | 0.5 day | Low |
| Phase 1 — `pergenFetch` wrapper | 1 day | Medium (wide-blast mechanical refactor) |
| Phase 2 — CSRF infra | 1 day | Low |
| Phase 3 — `auth_bp` + gate dual-path + immutability | 2 days | Medium-High (touches the security gate) |
| Phase 4 — throttling + audit + docs | 0.5 day | Low |
| **Total** | **~5 days** focused work | One Medium-High touch (Phase 3.7) |

**Headcount:** single developer plus mandatory `security-reviewer` and `code-reviewer` agent passes.

**Diff footprint estimate:**
- New files: 8 (1 blueprint, 1 security helper, 6 tests)
- Modified files: 4 (`app.js`, `index.html`, `app_factory.py`, `playwright.config.ts`)
- Net new code: ~600-800 LoC, ~80% of which is tests.

**Reversibility:** High. The legacy `X-API-Token` header path remains — disabling the cookie path is a one-line revert of the `auth_bp` registration plus deleting the new gate branch.

---

## 10. Success Criteria

- [ ] SPA loads and operates fully against a production-config Pergen with the token gate enforced, with no operator pasting tokens.
- [ ] `tests/test_security_token_gate_immutable.py` is required-pass (no longer xfail).
- [ ] `tests/test_security_csrf_required.py` is required-pass for every POST/PUT/DELETE route.
- [ ] All 73 SPA fetch call sites flow through `pergenFetch` (static-grep test green).
- [ ] Cookie carries `HttpOnly; SameSite=Lax`; `Secure` set when config says so; never contains the raw API token.
- [ ] `g.actor` is populated correctly under both auth paths; audit lines remain attributable.
- [ ] Failed login throttle returns 429 with `Retry-After` after 10 failures within 60s from one IP.
- [ ] `HOWTOUSE.md`, `ARCHITECTURE.md`, and new `docs/deploy/auth.md` describe the layered model and explicitly retain Option A as a valid additional layer.
- [ ] `patch_notes.md` deferred-work table closes both the *SPA auth UI gap* and *Token-gate immutability* rows.
- [ ] `security-reviewer` agent reports no CRITICAL/HIGH issues on the Phase 3 diff.
