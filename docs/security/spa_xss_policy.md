# SPA XSS Policy

> **Scope**: every dynamic `element.innerHTML = ...` write in
> `backend/static/js/app.js` (the single SPA bundle).
>
> **Status**: enforced.
>
> **Owner**: Frontend / Security.
>
> **Verified 2026-04-23** (wave-7 audit re-sweep): policy still accurate;
> `tests/test_security_innerhtml_lint.py` still passes; CSP `script-src 'self'`
> + `style-src 'self'` still in effect; no new UNSAFE sites were introduced
> by wave-6 Phase D / F or any subsequent commit. The wave-7 review
> (`docs/security/DONE_audit_2026-04-23-wave7.md` §3.3 M-7) flagged that
> `safeHtml` does NOT defend against `javascript:` URLs in attribute
> position — that is a defence-in-depth follow-up, not a regression in
> the existing policy.

---

## The rule (one paragraph)

Every dynamic `element.innerHTML = ...` write **MUST** route every
interpolation through one of:

1. `escapeHtml(value)` — for single-value or hand-built concatenations.
2. The `safeHtml` tagged template literal — for multi-fragment markup.
3. `textContent` / `dataset` / `setAttribute` — when no HTML structure
   is needed at all (preferred whenever possible).

A constant-only assignment (`= "<table>...</table>"`) or a clear
(`= ""`) is allowed verbatim. Anything that interpolates server data,
URL params, inventory hostnames, BGP API responses, NAT rule names,
device IPs, credential names, or any other untrusted source must be
escaped.

If a line genuinely cannot be classified by the regex but is provably
safe (a string concatenation of constants, or a variable that is itself
built fully through escapeHtml), annotate it on the same line or the
line immediately above:

```js
// xss-safe: rows is built entirely from escapeHtml() in the .map() above
body.innerHTML = "<table>" + rows + "</table>";
```

Annotations are checked by `tests/test_security_innerhtml_lint.py` and
must be specific enough that a reviewer can verify the claim from the
adjacent code.

---

## The helpers

### `escapeHtml(value)`

Lives in two places (kept in sync; tested by `tests/frontend/unit/utils.spec.ts`):

* `backend/static/js/app.js` — used by the SPA at runtime.
* `backend/static/js/lib/utils.js` — exported for Vitest.

**Encodes all five HTML entities**:

| Char | Encoded |
|------|---------|
| `&`  | `&amp;` |
| `<`  | `&lt;`  |
| `>`  | `&gt;`  |
| `"`  | `&quot;` |
| `'`  | `&#39;` |

This makes the result safe in **both** text-content and attribute-value
contexts. (The historical `textContent → innerHTML` round-trip did NOT
encode `"` or `'`; that gap was the H-02 attribute-injection class.
Wave-6 Phase C closes it permanently with a manual five-replace
implementation that runs identically in browser and Node.)

`null` and `undefined` return the empty string. Numbers are coerced to
their decimal string representation.

### ``safeHtml`...` ``

Tagged-template helper. Auto-escapes every `${...}` interpolation
through `escapeHtml`. Returns a plain string.

```js
// Multi-fragment markup — preferred when there are 2+ interpolations.
tbody.innerHTML = safeHtml`<tr><td>${name}</td><td>${ip}</td></tr>`;

// Equivalent but error-prone version:
tbody.innerHTML = "<tr><td>" + escapeHtml(name) + "</td><td>" + escapeHtml(ip) + "</td></tr>";
```

### `textContent` / `dataset` / `setAttribute`

The safest path. Use whenever the value is text only (no nested markup):

```js
status.textContent = errorMessage;       // safe — no HTML parsing at all
li.dataset.hostname = d.hostname;        // safe — DOM property, not HTML
btn.setAttribute("title", d.hostname);   // safe — DOM API, not HTML
```

CSS attribute-selector lookups for these stored values must use
`CSS.escape(value)` (not `.replace(/"/g, "&quot;")` — that is the wrong
escape for CSS-attribute-selector syntax):

```js
const li = listEl.querySelector(`li[data-hostname="${CSS.escape(name)}"]`);
```

---

## Enforcement layers

1. **Write-time** — code reviewers reject any new `.innerHTML = ...`
   write that interpolates a non-constant value without one of the
   helpers above.
2. **CI lint** — `tests/test_security_innerhtml_lint.py` reads
   `backend/static/js/app.js`, classifies every assignment, and fails
   the build if an UNSAFE assignment lacks a `// xss-safe` annotation.
3. **Advisory classifier** — `node scripts/audit/innerhtml_classifier.mjs`
   produces `docs/refactor/innerhtml_audit_report.csv` with the full
   bucket breakdown (SAFE-CONST / SAFE-CLEAR / SAFE-ESCAPED / PARTIAL /
   UNSAFE / UNSAFE-ANNOTATED) — useful when triaging or expanding the
   audit.
4. **Runtime regression** —
   `tests/e2e/specs/xss-innerhtml-regression.spec.ts` mocks each
   high-risk renderer (dropdowns, router-bgp table, BGP announced-prefix
   chip list, find-leaf device list) with the canonical XSS canary
   `<img src=x onerror='window.__xss=1'>` and asserts that no script
   executes and no live `<img src="x">` element appears in the DOM.
5. **CSP** — `Content-Security-Policy: script-src 'self'` blocks any
   inline script that did slip through; tested by
   `tests/e2e/specs/csp-no-inline.spec.ts`.

---

## What changed in Wave-6 Phase C

* `escapeHtml` migrated from DOM round-trip to manual five-entity
  replacement so attribute-context (`data-x="${escapeHtml(v)}"`) is now
  safe.
* New `safeHtml` tagged template helper added in both
  `app.js` and `lib/utils.js`.
* Three real UNSAFE renderers fixed:
  * `app.js:2987` (router-bgp table — peer_group, route_map names,
    prefix_list, prefixes, devices were all raw).
  * `app.js:2415` (BGP announced-prefixes chip list — partial-replace
    chain missed `>`, `&`, `'`).
  * `app.js:4067` (find-leaf device list — hostname injected raw into
    `<span>` body).
* Selector lookup at `app.js:4192` switched from
  `.replace(/"/g, "&quot;")` (wrong escape for CSS-attribute syntax) to
  `CSS.escape(...)`.
* New CI lint test, new Vitest tests, new Playwright XSS regression spec.
* Audit classifier script committed under `scripts/audit/` for future
  passes.
