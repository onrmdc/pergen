# How to Use Everything Claude Code (ECC) in Cursor

A practical guide to developing software efficiently with ECC agents, commands, hooks, rules, and skills in Cursor IDE.

---

## Table of Contents

1. [What is ECC?](#1-what-is-ecc)
2. [Your Setup](#2-your-setup)
3. [The Development Workflow](#3-the-development-workflow)
4. [Commands Reference](#4-commands-reference)
5. [Agents Reference](#5-agents-reference)
6. [Rules (Automatic)](#6-rules-automatic)
7. [Hooks (Automatic)](#7-hooks-automatic)
8. [Skills (Reference Knowledge)](#8-skills-reference-knowledge)
9. [Workflow Examples](#9-workflow-examples)
10. [Tips and Best Practices](#10-tips-and-best-practices)

---

## 1. What is ECC?

ECC is a performance optimization system for AI coding agents. It provides:

- **28 specialized agents** that handle specific tasks (planning, reviewing, testing, etc.)
- **60 commands** you can invoke in the Cursor chat
- **65+ rules** that automatically guide the AI's behavior when writing code
- **16 hooks** that fire automatically on events (file edits, shell commands, prompts)
- **54 skills** that provide domain knowledge (Django patterns, Python testing, API design, etc.)

You do not need to memorize all of these. The rules and hooks work automatically in the background. The commands and agents are what you actively use.

---

## 2. Your Setup

### Global Installation (applies to every project)

All ECC components are installed at `~/.cursor/`:

```
~/.cursor/
  rules/       65 rule files (auto-applied based on file type)
  agents/      28 agent definitions
  commands/    60 slash commands
  skills/      54 skill directories
  hooks/       16 hook scripts + adapter
  hooks.json   hook configuration (absolute paths)
  scripts/     shared hook scripts
```

### Per-Project Installation (optional, for project-specific config)

Run from inside any new project directory:

```bash
~/ccode-test-project/everything-claude-code/init-ecc-project.sh
```

### Updating

Pull the latest ECC and refresh all global files:

```bash
~/ccode-test-project/everything-claude-code/update-ecc-cursor.sh
```

---

## 3. The Development Workflow

ECC enforces a specific development workflow. This is the recommended sequence for building any feature:

```
PLAN  -->  TDD  -->  IMPLEMENT  -->  REVIEW  -->  VERIFY  -->  COMMIT
```

### Phase 1: Plan

Before writing any code, plan the implementation:

```
You: /plan Add user authentication with session-based login
```

The **planner** agent will:
- Restate your requirements
- Break the work into phases
- Identify dependencies and risks
- Estimate complexity
- **Wait for your confirmation** before proceeding

### Phase 2: Test-Driven Development

Once the plan is approved, implement using TDD:

```
You: /tdd Implement the login endpoint from Phase 1 of the plan
```

The **tdd-guide** agent will:
1. Define interfaces/types first
2. Write failing tests (RED)
3. Write minimal code to pass (GREEN)
4. Refactor while keeping tests green (IMPROVE)
5. Verify 80%+ test coverage

### Phase 3: Code Review

After implementation, review the code:

```
You: /code-review
```

For Python-specific review:

```
You: /python-review
```

The reviewer checks for:
- Security vulnerabilities (CRITICAL)
- Code quality issues (HIGH)
- Best practice violations (MEDIUM)
- Style issues (LOW)

### Phase 4: Verify

Run a comprehensive verification before committing:

```
You: /verify
```

This runs: build check, type check, lint, tests, coverage, and git status. It produces a pass/fail report telling you if the code is ready for a PR.

### Phase 5: Commit

Once verification passes, commit with conventional commit format:

```
You: Please commit with message "feat: add session-based user authentication"
```

---

## 4. Commands Reference

Commands are invoked in the Cursor chat by typing `/command-name` or just asking the AI to use a specific command. Here are the most important ones grouped by purpose:

### Planning and Architecture

| Command | What It Does |
|---------|-------------|
| `/plan` | Create a step-by-step implementation plan. Waits for your confirmation before coding. |
| `/orchestrate` | Coordinate multiple agents for a complex task |

### Code Quality

| Command | What It Does |
|---------|-------------|
| `/tdd` | Enforce test-driven development (tests first, then implementation) |
| `/code-review` | Review uncommitted changes for security and quality |
| `/python-review` | Python-specific review (PEP 8, type hints, Django/Flask patterns) |
| `/build-fix` | Incrementally fix build/type errors one at a time |
| `/refactor-clean` | Find and remove dead code safely |
| `/test-coverage` | Analyze test coverage and identify gaps |

### Verification and Deployment

| Command | What It Does |
|---------|-------------|
| `/verify` | Run full verification (build, types, lint, tests, coverage) |
| `/verify quick` | Quick check (build + types only) |
| `/verify pre-pr` | Full checks plus security scan |
| `/e2e` | Generate and run end-to-end Playwright tests |

### Documentation

| Command | What It Does |
|---------|-------------|
| `/update-docs` | Update project documentation |
| `/update-codemaps` | Update code maps |
| `/docs` | Look up library/API documentation |

### Go-Specific

| Command | What It Does |
|---------|-------------|
| `/go-review` | Go code review (idioms, concurrency, error handling) |
| `/go-test` | Go TDD workflow |
| `/go-build` | Fix Go build errors |

### Session Management

| Command | What It Does |
|---------|-------------|
| `/checkpoint` | Save current verification state |
| `/learn` | Extract patterns from the current session |
| `/save-session` | Save session state |
| `/resume-session` | Resume a previous session |

---

## 5. Agents Reference

Agents are specialized AI personas that handle specific tasks. They are invoked automatically by commands, or you can ask for them directly. For example: "Use the architect agent to design the database schema."

### Core Agents (Use Most Often)

| Agent | Purpose | When to Use |
|-------|---------|-------------|
| **planner** | Creates implementation plans | Starting new features, complex changes |
| **architect** | System design and scalability decisions | Database schema, API design, service architecture |
| **tdd-guide** | Enforces test-first development | Every new feature or bug fix |
| **code-reviewer** | Reviews code for quality and security | After every code change |
| **security-reviewer** | Finds vulnerabilities (OWASP Top 10) | Before commits, auth/input handling code |
| **build-error-resolver** | Fixes build/compilation errors | When the build breaks |

### Language-Specific Reviewers

| Agent | Purpose |
|-------|---------|
| **python-reviewer** | PEP 8, type hints, Django/Flask patterns, security |
| **go-reviewer** | Go idioms, concurrency, error handling |
| **typescript-reviewer** | TypeScript/JavaScript type safety, async patterns |
| **rust-reviewer** | Ownership, lifetimes, unsafe usage |

### Specialized Agents

| Agent | Purpose |
|-------|---------|
| **e2e-runner** | Generates and runs Playwright E2E tests |
| **refactor-cleaner** | Finds and removes dead code |
| **doc-updater** | Updates documentation and code maps |
| **docs-lookup** | Looks up library/API documentation |
| **database-reviewer** | PostgreSQL query optimization, schema design |

### How Agents Are Triggered

1. **By commands**: `/plan` triggers the planner, `/tdd` triggers tdd-guide, etc.
2. **Proactively by Cursor**: Some agents auto-activate based on context:
   - Writing code? The code-reviewer activates after changes
   - Build broke? The build-error-resolver activates
   - Security-sensitive code? The security-reviewer flags issues
3. **By request**: Ask "use the architect agent to..." in the chat

---

## 6. Rules (Automatic)

Rules run automatically in the background. You do not need to invoke them. They guide the AI's behavior when writing code.

### Common Rules (Always Active)

These apply to every file in every project:

| Rule | What It Enforces |
|------|-----------------|
| `common-coding-style` | Small functions (<50 lines), small files (<800 lines), immutability |
| `common-security` | Input validation, no hardcoded secrets, OWASP compliance |
| `common-testing` | 80%+ coverage, TDD workflow, edge case testing |
| `common-git-workflow` | Conventional commits, PR workflow |
| `common-patterns` | Repository pattern, API response format, skeleton projects |
| `common-performance` | Context window management, model selection |
| `common-agents` | When to delegate to specialized agents |
| `common-hooks` | Hook architecture and TodoWrite usage |

### Language-Specific Rules (Activate by File Type)

These only activate when you are editing files of the matching type:

| Rule Set | Activates On | What It Enforces |
|----------|-------------|-----------------|
| `python-*` | `**/*.py` | PEP 8, type hints, Django/Flask patterns, pytest |
| `typescript-*` | `**/*.ts`, `**/*.tsx` | Strict TypeScript, async patterns, React best practices |
| `golang-*` | `**/*.go` | Go idioms, error handling, concurrency |

Each language has 5 rule files: coding-style, hooks, patterns, security, testing.

---

## 7. Hooks (Automatic)

Hooks fire automatically on specific events. You do not invoke them manually.

### What Hooks Do

| Hook Event | What Happens |
|------------|-------------|
| **sessionStart** | Loads previous context and detects your environment |
| **sessionEnd** | Saves session state and extracts patterns |
| **beforeShellExecution** | Blocks risky commands, reminds about tmux for dev servers |
| **afterShellExecution** | Logs PR URLs, analyzes build output |
| **afterFileEdit** | Auto-formats code, runs TypeScript check, warns about console.log |
| **beforeSubmitPrompt** | Detects secrets in your prompts (API keys, tokens) |
| **beforeReadFile** | Warns when reading sensitive files (.env, .key, .pem) |
| **beforeTabFileRead** | Blocks Tab autocomplete from reading secrets |
| **beforeMCPExecution** | Logs MCP tool usage, warns about untrusted servers |
| **stop** | Audits all modified files for console.log statements |

### Hook Profiles

Control how strictly hooks enforce rules via environment variable:

```bash
# Minimal — only critical hooks (secret detection, blocking)
export ECC_HOOK_PROFILE=minimal

# Standard — balanced enforcement (default)
export ECC_HOOK_PROFILE=standard

# Strict — all hooks active, maximum enforcement
export ECC_HOOK_PROFILE=strict
```

### Disabling Specific Hooks

```bash
# Disable the tmux reminder and typecheck hooks
export ECC_DISABLED_HOOKS="pre:bash:tmux-reminder,post:edit:typecheck"
```

---

## 8. Skills (Reference Knowledge)

Skills are knowledge bases that agents reference when working on specific domains. You do not invoke skills directly — agents read them when relevant.

### Python/Django Skills

| Skill | What It Provides |
|-------|-----------------|
| `python-patterns` | Python idioms, OOP, async, packaging best practices |
| `python-testing` | pytest patterns, fixtures, mocking, coverage |
| `django-patterns` | Models, views, serializers, middleware, signals |
| `django-tdd` | Django-specific TDD with pytest-django |
| `django-verification` | Django verification loops and deployment checks |

### Backend/API Skills

| Skill | What It Provides |
|-------|-----------------|
| `api-design` | REST API design, pagination, error responses, versioning |
| `backend-patterns` | Database patterns, caching strategies, queue patterns |

### Testing Skills

| Skill | What It Provides |
|-------|-----------------|
| `tdd-workflow` | TDD methodology, Red-Green-Refactor cycle |
| `e2e-testing` | Playwright patterns, Page Object Model |
| `verification-loop` | Build, test, lint, typecheck, security verification |

### Security Skills

| Skill | What It Provides |
|-------|-----------------|
| `coding-standards` | Universal coding standards across languages |
| `security-review` | OWASP Top 10 checklist, vulnerability patterns |

### Infrastructure Skills

| Skill | What It Provides |
|-------|-----------------|
| `mcp-server-patterns` | Building MCP servers |
| `strategic-compact` | When to compact context to avoid quality degradation |
| `continuous-learning` | Auto-extract patterns from coding sessions |

---

## 9. Workflow Examples

### Example 1: Building a New Django REST API

```
Step 1 — Plan the feature:
You: /plan Build a REST API for network device inventory with CRUD operations

Step 2 — The planner creates phases (models, serializers, views, tests)
You: Looks good, proceed

Step 3 — Implement with TDD:
You: /tdd Implement the Device model and serializer from Phase 1

Step 4 — Continue with next phase:
You: /tdd Implement the DeviceViewSet with list, create, update, delete

Step 5 — Review Python code:
You: /python-review

Step 6 — Run full verification:
You: /verify

Step 7 — Fix any issues:
You: /build-fix    (if build errors)

Step 8 — Commit:
You: Please commit these changes
```

### Example 2: Fixing a Bug

```
Step 1 — Write a failing test that reproduces the bug:
You: /tdd The BGP parser crashes when neighbor has no AS number. Write a test that reproduces this.

Step 2 — The tdd-guide writes a failing test, then implements the fix

Step 3 — Review the fix:
You: /code-review

Step 4 — Verify nothing else broke:
You: /verify
```

### Example 3: Refactoring Existing Code

```
Step 1 — Plan the refactoring:
You: /plan Refactor the runner module to use abstract base classes

Step 2 — Clean up dead code first:
You: /refactor-clean

Step 3 — Implement the refactoring with TDD:
You: /tdd Implement the BaseRunner ABC and AristaRunner subclass

Step 4 — Review:
You: /code-review

Step 5 — Verify:
You: /verify
```

### Example 4: Designing System Architecture

```
You: Use the architect agent to design the service layer for a network
     automation platform that handles device discovery, configuration
     backup, and compliance checking.

The architect agent will:
- Analyze your requirements
- Propose a layered architecture
- Suggest design patterns (Factory, Strategy, Observer)
- Identify scalability considerations
- Recommend technology choices
- Present trade-offs for your decision
```

### Example 5: Security Audit Before Release

```
Step 1 — Run security review:
You: Use the security-reviewer agent to audit the entire codebase

Step 2 — Run full pre-PR verification:
You: /verify pre-pr

Step 3 — Run E2E tests on critical flows:
You: /e2e Test the login and device management flows

Step 4 — Check test coverage:
You: /test-coverage
```

---

## 10. Tips and Best Practices

### Do

- **Always start with `/plan`** for features that touch more than 2-3 files
- **Always use `/tdd`** — writing tests first catches design issues early
- **Run `/code-review` or `/python-review`** after every significant change
- **Run `/verify`** before every commit
- **Use the architect agent** for database schema and API design decisions
- **Let hooks work for you** — they catch secrets, formatting issues, and risky commands automatically

### Do Not

- Do not skip the planning phase for complex features
- Do not write code before tests (the tdd-guide enforces this)
- Do not ignore CRITICAL or HIGH issues from code review
- Do not commit without running `/verify`
- Do not hardcode any secrets, API keys, or passwords
- Do not disable security hooks unless absolutely necessary

### Context Window Management

ECC rules enforce context-aware behavior:

- Keep under 10 MCP servers enabled per project
- Use `/compact` at logical breakpoints (after research, before implementation)
- Use `/clear` between unrelated tasks

### Command Chaining

Commands work best in sequence:

```
/plan  -->  /tdd  -->  /code-review  -->  /verify  -->  commit
```

For bug fixes:

```
/tdd (reproduce bug)  -->  /code-review  -->  /verify  -->  commit
```

For refactoring:

```
/plan  -->  /refactor-clean  -->  /tdd  -->  /code-review  -->  /verify
```

### Quick Reference Card

| I want to... | Use |
|-------------|-----|
| Plan a new feature | `/plan "description"` |
| Design system architecture | Ask for the architect agent |
| Write code with tests first | `/tdd "what to implement"` |
| Review my code changes | `/code-review` or `/python-review` |
| Fix build errors | `/build-fix` |
| Run all checks before commit | `/verify` |
| Generate E2E tests | `/e2e "what to test"` |
| Find security vulnerabilities | Ask for the security-reviewer agent |
| Remove dead code | `/refactor-clean` |
| Update documentation | `/update-docs` |
| Look up a library's API | `/docs` |
| Check test coverage | `/test-coverage` |

---

## File Locations

| Component | Global (all projects) | Per-Project |
|-----------|----------------------|-------------|
| Rules | `~/.cursor/rules/` | `.cursor/rules/` |
| Agents | `~/.cursor/agents/` | `.cursor/agents/` |
| Commands | `~/.cursor/commands/` | `.cursor/commands/` |
| Skills | `~/.cursor/skills/` | `.cursor/skills/` |
| Hooks | `~/.cursor/hooks.json` | `.cursor/hooks.json` |
| AGENTS.md | N/A | Project root |
| MCP config | N/A | `.cursor/mcp.json` |

Project-level files override global files when both exist.

---

## Maintenance Scripts

```bash
# Update ECC globally (pull latest + refresh ~/.cursor/)
~/ccode-test-project/everything-claude-code/update-ecc-cursor.sh

# Initialize ECC in a new project directory
cd /path/to/new-project
~/ccode-test-project/everything-claude-code/init-ecc-project.sh

# Initialize with specific languages
~/ccode-test-project/everything-claude-code/init-ecc-project.sh python golang
```

---

## Project-specific notes (Pergen)

This guide is the generic ECC reference. For Pergen-specific operational
knowledge use the project's own docs:

- **Test counts and reproducibility:** [`TEST_RESULTS.md`](./TEST_RESULTS.md) — current `1767 + 1 xfailed` pytest, `45` Vitest, `100 / 100` Playwright; coverage `90.79 %` whole-project / `91.34 %` OOD-scoped.
- **Operational env vars** (including the wave-7 additions `PERGEN_SESSION_LIFETIME_HOURS`, `PERGEN_SESSION_IDLE_HOURS`, `PERGEN_TRUST_PROXY`, `PERGEN_DEV_BIND_HOST`, `PERGEN_DEV_ALLOW_PUBLIC_BIND`): [`HOWTOUSE.md`](./HOWTOUSE.md) §3.
- **Architecture** (App Factory + 12 blueprints + service layer + repository layer + parser package): [`ARCHITECTURE.md`](./ARCHITECTURE.md).
- **Per-class function reference:** [`FUNCTIONS_EXPLANATIONS.md`](./FUNCTIONS_EXPLANATIONS.md).
- **Latest changelog:** [`patch_notes.md` v0.7.1](./patch_notes.md) — wave-7 audit followup (1 CRITICAL + 6 HIGH + 2 Python CRITICAL fixes; 12 Playwright specs stabilised).
- **Latest security audit:** [`docs/security/DONE_audit_2026-04-23-wave7.md`](./docs/security/DONE_audit_2026-04-23-wave7.md).
