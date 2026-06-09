# Forensic Code Review — datacommons-mcp

**Date:** 2026-06-08
**Branch reviewed:** `main` (HEAD `d111d21`, v1.2.2)
**Method:** Six parallel read-only analysis agents (architecture, dead-code/hygiene, MCP/FastMCP standards, security, testing/CI, dependencies/packaging), each citing `file:line` evidence, synthesized here.
**Repo:** public — `cfdude/datacommons-mcp`, a stagnated fork of `datacommonsorg/agent-toolkit`.

---

## Executive Summary

`datacommons-mcp` is a **stateless, read-only FastMCP server** that proxies the Data Commons knowledge graph and exposes exactly two MCP tools (`search_indicators`, `get_observations`), streaming large result sets to CSV/JSON files. The **core engineering is more sound than its reputation** — clean dependency injection, no problematic global state, no real import cycles, 78% test coverage, and a genuinely good large-response file-export pattern. The problems are **drift, dead weight, security debt, and packaging/CI gaps** accumulated since the fork — not a rotten core.

**The headline issues:**

1. **Security debt is the most urgent item.** 22 real dependency CVEs (Trivy), including **Critical** CVEs in `fastmcp` and `authlib`; the core framework is pinned to a **beta** (`fastmcp>=3.0.0b1`); Dependabot and secret scanning are **disabled**; and `evals.yaml` carries a **`pull_request_target` + untrusted-checkout footgun** (Critical-by-design, currently un-exploitable only because no secrets exist yet).
2. **Dead weight from the upstream fork can be cut wholesale.** The entire Google ADK / Gemini surface (`evals/`, `examples/`, `evals.yaml`) is non-functional (imports `google.adk`, which isn't even a dependency) and should be deleted — this is exactly the "sever the upstream tie" the owner wants.
3. **Configuration is triplicated** and three modules exceed 500–1224 LOC, but these are consolidation/refactor problems with low blast radius, not rewrites.
4. **No database is warranted** — every agent independently concluded that **SQLAlchemy/Alembic should NOT be adopted** (no persistent relational state). FastAPI is declared but unused and should be dropped until an HTTP API actually exists.

**Three premises going in were FALSE and are corrected here:** there is **no committed `.env`/secret** (only a placeholder `.env.sample`); there is **no duplicate `server.py`** (the entry chain is coherent); and the FastMCP fix direction is **forward to 3.x stable** (3.0 is GA at 3.4.2) — the server's own "pin < 3" warning is stale advice.

---

## Top Findings (cross-cutting, severity-ranked)

| # | Severity | Finding | Where | Fix direction |
|---|----------|---------|-------|---------------|
| 1 | **Critical** | `fastmcp>=3.0.0b1` ships a **beta**, **unbounded**, with **Critical CVE-2026-32871**. 3.0 is GA (3.4.2). | `pyproject.toml:17`, `uv.lock` | Pin `fastmcp>=3.4,<4`; `uv lock`; run tests against GA. |
| 2 | **Critical** | `authlib 1.6.6` has **6 CVEs** (1 Critical). Transitive via fastmcp. | `uv.lock` | Upgrade to `1.6.12`/`1.7.1` (largely follows the fastmcp bump). |
| 3 | **Critical** | `evals.yaml` uses `pull_request_target` + checks out & executes PR `head.sha` in a secret-bearing context. | `evals.yaml:7,45-49,78-79` | Delete the workflow (eval suite is dead); never run untrusted checkout with secrets. |
| 4 | **High** | Dependabot **disabled**, no `dependabot.yml`; secret scanning **disabled**; CodeQL default setup `not-configured` (4 stale alerts linger). | repo settings | Enable all; add `dependabot.yml`; re-run CodeQL (auto-closes the 4 stale, already-fixed alerts). |
| 5 | **High** | 20 more real Trivy dependency CVEs (cryptography, pyjwt, urllib3, requests, python-multipart, python-dotenv, pytest, pygments; `diskcache` has no fix yet). | `uv.lock` | `uv lock --upgrade-package …`; triage `diskcache`. |
| 6 | **High** | Dead upstream weight: `evals/`, `examples/`, `evals.yaml` (all `google.adk`/Gemini; undeclared dep; can't run). | repo tree | Delete; trim ADK/agent references from docs. |
| 7 | **High** | Configuration triplicated: `config.py` + `data_models/settings.py` + `settings.py` model the same env vars. | those files, `servers/base.py:92-113` | Collapse to one `Settings` class; delete `_Compat*` shims + `get_output_settings()`. |
| 8 | **High** | Unused deps: `fastapi`, `tiktoken`, `respx`; redundant `httpx`; **`click` used but undeclared**. | `pyproject.toml` | Drop unused, declare `click`, bound all deps. **Do not add SQLAlchemy/Alembic.** |
| 9 | **High** | PyPI publish has **no test/lint gate**; no coverage gate; no type-checking; CI matrix omits 3.13. | `build-and-publish*.yaml`, `ci.yaml` | Gate publish on CI; add `--cov-fail-under`, mypy, 3.13 leg. |
| 10 | **High** | Tools return bare `dict`, discarding Pydantic schemas → no FastMCP **structured output**. | `observations.py:49`, `search.py:321-332` | Return typed models / discriminated unions. |
| 11 | **Medium** | God modules: `clients.py` (1224), `services.py` (838), `topics.py` (543). | those files | Split by responsibility (see Architecture target). |
| 12 | **Medium** | Committed runtime data CSV; flat layout; stale `__pycache__`; half-migrated extension (dead `lib/` sys.path code, vestigial manifest `entry_point`). | repo tree, `run_server.py:26-34`, `manifest.json:16` | `git rm` data, gitignore; move to `src/`; finish the uv-runtime migration. |
| 13 | **Low** | `evals-and-secrets` GitHub Environment: 0 secrets, 0 protection rules — implies a deployment that doesn't exist. | repo settings, `evals.yaml:21` | Delete environment + the `environment:` line. |

---

<!-- The six sections below are the verbatim deep-dive outputs of the parallel analysis agents. -->

## Architecture & Code Organization

### Current State

`datacommons-mcp` is a **FastMCP-based, read-only API-proxy server** for the Data Commons knowledge graph. It exposes exactly two MCP tools — `search_indicators` and `get_observations` — over stdio or Streamable HTTP. There is **no database, no persistent state, and no write path**: the server resolves places/variables via the Data Commons HTTP API, optionally caches topic hierarchies in-process and on disk as JSON, and streams large result sets to CSV/JSON files. ~6,932 LOC across the `datacommons_mcp/` package, plus 16 test files in `tests/`.

**Composition / layering** (verified clean DI, top to bottom):

1. **Transport / entry**: `cli.py` (`serve http` / `serve stdio` via Click) and `run_server.py` (standalone script for the Claude Desktop extension) both import `mcp` from `fastmcp_server.py`.
2. **Server assembly**: `fastmcp_server.py:35-41` imports the tool modules for their decorator side effects, then re-exports the `mcp` instance created in `servers/base.py`. `base.py` owns the singleton `FastMCP` instance and the `dc_lifespan` async context manager (`base.py:100-178`) which builds all shared resources once and yields them in a context dict.
3. **Tools**: `servers/search.py` and `servers/observations.py` define the two `@mcp.tool` functions, pull dependencies from the lifespan context via `servers/common.py`, and delegate to the service layer.
4. **Services**: `services.py` — pure async functions that **receive `client: DCClient` as a parameter** (clean DI, `services.py:335`, `557`). No global state.
5. **Clients**: `clients.py` — `DCClient` wraps `datacommons_client.DataCommonsClient`, holds per-instance caches/topic store, does all HTTP/transform work.
6. **Domain models / support**: `data_models/` (Pydantic models + settings), `topics.py` (TopicStore + cache I/O), `utils/` (output/pagination/CSV/path), `cache.py`, `exceptions.py`.

**What is clean (verified):** no problematic mutable global singletons; no real import cycles (cross-layer back-references are `TYPE_CHECKING`-only); service-layer DI makes services independently testable; the two-tool surface is appropriately small.

### Problems

| Severity | Issue | Location | Impact |
|---|---|---|---|
| High | **Triple/parallel configuration system.** `AppConfig` (`config.py:38`) and `BaseDCSettings`/`CustomDCSettings`/`OutputSettings` (`data_models/settings.py`) model the same env vars; lifespan builds **both** (`base.py:112-113`); `settings.py` adds a third name. | `config.py`, `settings.py`, `data_models/settings.py:32-100`, `base.py:92-113` | Same env vars parsed by two schemas; drift risk; every config change touches two files. |
| High | **God module `clients.py` (1,224 LOC).** `DCClient` mixes ≥5 responsibilities: search-index config, caching, pagination, topic expansion/existence filtering, response transformation, plus 4 factory functions. | `clients.py:69-1121` | Hard to test, high cognitive load; transform/topic logic doesn't belong on an HTTP client. |
| High | **God module `services.py` (838 LOC).** Two public orchestrators + ~15 helpers spanning observations and search — two domains in one flat file. | `services.py:53-816` | Two unrelated workflows entangled; no module boundary. |
| Medium | **God module `topics.py` (543 LOC)** conflates the `TopicStore` model + traversal with cache I/O / serialization. | `topics.py:38-442` | Model can't be imported without file-I/O machinery. |
| Medium | **Vestigial alternate config path.** `OutputHandlerConfig.from_settings()` → `get_output_settings()` only fires when `settings is None`; the live lifespan path always passes explicit config. | `utils/output_handler.py:62-66,112`, `base.py:127-137` | Dead-but-loaded second config path. |
| Medium | **Service code mis-filed as `utils/`.** `output_handler.py`, `pagination_handler.py` import `DCClient` and orchestrate — they're services, not utils. | `utils/output_handler.py`, `utils/pagination_handler.py` | "utils" becomes a junk drawer. |
| Medium | **Backward-compat shims with no consumer.** `_CompatStorage`/`_CompatOutput` (`config.py:191-232`); `settings.py` 1-function re-export. | `config.py:191-232`, `settings.py` | Dead abstraction. |
| Medium | **FastAPI declared but unused.** `fastapi>=0.100.0` is a hard dep but nothing imports it; HTTP is FastMCP's own `streamable-http`. | `pyproject.toml:15`, `cli.py:80` | Unnecessary dependency surface. |
| Low | **Stale bytecode for non-existent `server.py`.** No `server.py` in tree or history; only a stale `__pycache__/server.cpython-312.pyc`. | `datacommons_mcp/__pycache__/` | Misleads readers; `__pycache__` not cleanly gitignored. |
| Low | Inline import mid-file (`clients.py:36-46`, E402 globally suppressed); `cli.py` blanket `except ImportError` can mask real load-time bugs (`cli.py:82-84,120-122`). | as cited | Minor hygiene / hidden failures. |

### Target Architecture

This is a 2-tool, stateless API proxy. The right "overhaul" is **consolidation of drift, not added infrastructure**. **No DB is warranted** → do NOT adopt SQLAlchemy/Alembic. **Drop FastAPI** unless custom HTTP routes are genuinely needed (FastMCP already serves Streamable HTTP). Keep Python + pytest + FastMCP + Pydantic. Move to a `src/` layout.

```
datacommons-mcp/
├── pyproject.toml                 # drop fastapi; no sqlalchemy/alembic
├── src/datacommons_mcp/
│   ├── version.py
│   ├── config.py                  # SINGLE Settings (merge config + data_models/settings + settings); delete _Compat*
│   ├── app.py                     # FastMCP instance + dc_lifespan (was servers/base.py)
│   ├── cli.py                     # Click entry; fix ImportError handling
│   ├── run_server.py              # extension shim
│   ├── tools/                     # MCP tool layer (was servers/)
│   │   ├── _context.py            # get_client/get_config (was servers/common.py)
│   │   ├── search.py
│   │   └── observations.py
│   ├── services/                  # SPLIT services.py by domain
│   │   ├── observations.py
│   │   ├── search.py
│   │   ├── output.py              # MOVED from utils/output_handler.py
│   │   └── pagination.py          # MOVED from utils/pagination_handler.py
│   ├── client/                    # SPLIT clients.py
│   │   ├── dc_client.py           # HTTP + paging primitives only
│   │   ├── transforms.py
│   │   └── existence.py
│   ├── topics/                    # SPLIT topics.py
│   │   ├── store.py               # model only
│   │   └── cache_io.py            # JSON serialization
│   ├── models/                    # was data_models/
│   ├── export/                    # genuine utils (csv_streamer, multi_file_exporter, path_resolver)
│   ├── cache.py, date_utils.py, exceptions.py
│   └── data/topics/*.json
└── tests/                         # mirror src/
```

### Recommendations (sequenced low-risk → high-value)

1. **(Low/High value) Unify configuration** — `AppConfig` canonical; fold others in; delete `settings.py`, `_Compat*`, `get_output_settings()`. No behavior change (defaults already match).
2. **(Low) Remove unused deps & dead code** — drop `fastapi`; clean stale `__pycache__`/`server.*.pyc`; reconcile `requests` vs `httpx`.
3. **(Medium) Split `services.py`** → `services/observations.py` + `services/search.py` (pure moves; DI unchanged).
4. **(Medium) Split `clients.py`** → `client/{dc_client,transforms,existence}.py`.
5. **(Medium) Split `topics.py`** → `topics/{store,cache_io}.py`.
6. **(Medium) Reclassify `utils/`** → move orchestrators to `services/`; keep stateless helpers in `export/`.
7. **(Higher, last) Adopt `src/` layout**; rename `servers/`→`tools/`, `data_models/`→`models/`.
8. **Do NOT add** SQLAlchemy/Alembic/DB. FastAPI only when real HTTP routes exist.
9. **Tighten `cli.py` error handling.**

---

## Dead Code, Orphaned Files & Repo Hygiene

### Premise correction
"A committed `.env` AND `.env.sample`" is **false**. `.env` is git-ignored (`.gitignore:131`) and never committed; only placeholder `.env.sample` is tracked. **No committed-secret incident.** Also: there is **no `server.py`** — the entry chain (`cli.py`/`run_server.py` → `fastmcp_server.py:35-41` → `servers/base.py` → `servers/{observations,search}.py`) is coherent, not duplicated. KEEP all of it.

### Inventory

| Item | Type | Tracked? | Blast radius | Recommendation |
|---|---|---|---|---|
| `data_models/charts.py` | Dead module | Yes | **Zero** importers (verified `rg`) | **DELETE** |
| `evals/` (whole tree) | Non-functional evals | Yes | Imports `google.adk` (undeclared dep); outside `testpaths`; needs keys; CI treats "0 collected" as pass | **DELETE** (+ `evals.yaml`) |
| `.github/workflows/evals.yaml` | Orphaned CI | Yes | Only runs `evals/` | **DELETE** |
| `examples/sample_agents/` | ADK/Gemini sample | Yes | Imports `google.adk`, `gemini-2.5-flash`; unused | **DELETE** |
| `functional_test.py` (root) | Manual smoke script | Yes | Not collected; `__main__` script | **DELETE** or **MOVE** to `scripts/`/`tests/` |
| `SPRINT_2_INTEGRATION.md` | Sprint doc | Yes | Process artifact | **DELETE** |
| `datacommons-data/observations/*.csv` | Runtime output | **Yes** (in `7f0a2f8`) | Runtime data in git; not gitignored | **`git rm`** + gitignore `datacommons-data/` |
| `datacommons_mcp/settings.py` (root) | Vestigial wrapper | Yes | `get_dc_settings()` imported **only by tests**; prod reimplements in `base.py:92-97` | **CONSOLIDATE** (not blind delete) |
| `build/`, `*.egg-info/`, `*.mcpb` | Build artifacts | No (ignored) | Local clutter | KEEP ignored; `rm` locally |
| `_constrained_vars.py` + its test | "temp"-named but **LIVE** (`clients.py:143`) | Yes | Active | **KEEP** (optional rename) |
| `utils/date_utils.py` | Suspected dead — **LIVE** (`services.py:163,188,235`) | Yes | Active | **KEEP** |

### Committed secrets / data leakage
- **No committed secrets.** Local `.env` holds a real key but is git-ignored and absent from history. **Action:** rotate the local `DC_API_KEY` as hygiene (it sat in plaintext locally), but it is not in the repo. **Low.**
- **Tracked runtime data** — `datacommons-data/observations/observations_Count_Person_*.csv` (public Census figures, not sensitive) was committed in `7f0a2f8`. `git rm` + gitignore `datacommons-data/`. **Low.**

### Prioritized cleanup
1. **High — sever the ADK/Gemini tie:** delete `evals/`, `examples/`, `evals.yaml` together; **trim ADK/agent references** from `README.md`, `docs/quickstart.md`, `docs/user_guide.md`, `docs/extension-compatibility.md`, `docs/internal/evals.md` (don't leave dangling refs).
2. **High — stop tracking runtime data:** `git rm datacommons-data/observations/*.csv`; gitignore the dir.
3. **Medium — delete dead code:** `charts.py`, `functional_test.py` (or move), `SPRINT_2_INTEGRATION.md`.
4. **Medium — de-duplicate settings:** have `base.py::_get_dc_settings()` use the shared helper, or remove the root wrapper and repoint the 6 test imports.
5. **Low — hygiene:** rotate local key; `rm` local build artifacts.

---

## MCP / FastMCP Standards Compliance

### Current Implementation
FastMCP server; two tools (`get_observations`, `search_indicators`), no resources/prompts. Composition: `servers/base.py` (instance + lifespan), `servers/observations.py` + `servers/search.py` (one `@mcp.tool` each), `servers/common.py` (context accessors), `fastmcp_server.py` (side-effect registration + `run_server()`). **No `server.py` exists.** Current/correct idioms in use: decorator registration with `tags`/`annotations` (`readOnlyHint`, `idempotentHint`); `Literal[...]` typed params; `Context` injection + async lifespan; stdio + Streamable HTTP transports; Pydantic v2 models; large-response file-export overflow (a genuinely good pattern).

### Standards Gaps

| Severity | Gap | Location | Modern standard |
|---|---|---|---|
| Critical | `fastmcp>=3.0.0b1` — stale **beta**, **no upper bound**; lock freezes the beta. 3.0 is GA (3.4.2). | `pyproject.toml:17`, `uv.lock:389,505` | Pin `fastmcp>=3.4,<4`; never ship a beta; always cap the major. |
| High | Both tools annotated `-> dict`, discarding Pydantic schemas (`search_indicators` builds `SearchResponse` then `.model_dump()`s it away). Forfeits FastMCP **structured output**. | `observations.py:49`, `search.py:321-332`, `output_handler.py:217-222` | Return typed models; use a **discriminated union** (`ScreenResult \| FileResult`) for `get_observations`. |
| Medium | `places: Union[list[str], str]` with manual `json.loads` workaround. | `search.py:38,302-318` | Declare `list[str] \| None`; use a validator if a client is known-broken. |
| Medium | Inconsistent error surfacing: `get_observations` bare-`raise` after stderr `print`; `search_indicators` no handler; service raises plain `ValueError`; `format_api_error()` is **dead** (`common.py:67`). | as cited | Raise `fastmcp.exceptions.ToolError` for client-facing errors; one error model; delete dead formatter. |
| Medium | `fastapi` declared but never imported. | `pyproject.toml:16` | Remove, or mount via `mcp.http_app()` if HTTP API is actually wanted. |
| Low | Server's "Pin fastmcp < 3" runtime warning is **stale** (predates GA); following it would be a downgrade to 2.x. | runtime | Disregard; move to 3.x stable. |
| Low | Stray `print(..., file=sys.stderr)` alongside `logging`/`ctx` — can interfere with stdio framing. | `observations.py:180`, `search.py:309-318` | Use `logging`/`ctx` consistently. |

### FastMCP beta-pin risk
**Verified:** FastMCP 3.0 is GA; latest stable 3.4.2; last 2.x is 2.14.5. The pin is Critical because it (1) ships a churny beta and (2) is unbounded (clean install could pull 4.0+). **Fix forward**: `fastmcp>=3.4,<4`, re-lock, run the suite against GA (this is where the `-> dict` and lifespan/`Context` idioms get re-validated). A 2.x pin is only warranted if a hard blocker surfaces.

### Modernization recommendations
1. **Upgrade off the beta (Critical, first).** 2. **Adopt structured output (High).** 3. **Standardize error model on `ToolError` (Medium); delete `format_api_error`.** 4. **Clean the `places` input contract (Medium).** 5. **Resolve FastAPI (remove or mount properly).** 6. **Keep the good parts** (minimal surface, lifespan resources, annotations, progress reporting, file-export overflow).

---

## Security Forensics

Audit date 2026-06-08. 26 open code-scanning alerts (4 CodeQL + 22 Trivy); Dependabot disabled; secret scanning disabled; CodeQL default-setup "not-configured."

### CodeQL (4 alerts) — ALL STALE / ALREADY FIXED
All four were generated at `fb4f870` and remediated in `9b20adf`. They remain open only because CodeQL default setup is "not-configured" and hasn't re-scanned. Verified against live files.

| # | Rule | Sev | Flagged at | Current state | Verdict |
|---|------|-----|-----------|---------------|---------|
| 1 | missing-workflow-permissions | Med | ci.yaml:13 | `permissions: contents: read` present | Fixed — noise |
| 2 | missing-workflow-permissions | Med | build-and-publish:12 | top-level + job-scoped present | Fixed — noise |
| 3 | unpinned-tag | Med | ci.yaml:26 | SHA-pinned (`@de90cc6…`) | Fixed — noise |
| 4 | unpinned-tag | Med | evals.yaml:38 | SHA-pinned | Fixed — noise |

Fix: re-run/configure CodeQL → auto-closes all 4. No code changes.

### Trivy (22 alerts) — REAL dependency CVEs in `uv.lock`

| Package | Installed | # | Highest Sev | Fixed | Notes |
|---------|-----------|---|-------------|-------|-------|
| **fastmcp** | 3.0.0b1 | 3 | **Critical** (CVE-2026-32871) + High + Med | **3.2.0+** | beta; top priority |
| **authlib** | 1.6.6 | 6 | **Critical** (CVE-2026-27962) + 3×High + 2×Med | **1.7.1 / 1.6.12** | auth lib; most CVEs |
| **cryptography** | 46.0.4 | 3 | High (CVE-2026-26007) | **46.0.7** | |
| **pyjwt** | 2.10.1 | 1 | High (CVE-2026-32597) | **2.12.0** | |
| **python-multipart** | 0.0.22 | 2 | High (CVE-2026-42561) | **0.0.27** | |
| **urllib3** | 2.6.3 | 2 | High (CVE-2026-44432) | **2.7.0** | |
| **requests** | 2.32.5 | 1 | Med (CVE-2026-25645) | **2.33.0** | |
| **python-dotenv** | 1.2.1 | 1 | Med (CVE-2026-28684) | **1.2.2** | |
| **pytest** | 8.4.2 | 1 | Med (CVE-2025-71176) | **9.0.3** | dev-only |
| **pygments** | 2.19.2 | 1 | Low (CVE-2026-4539) | **2.20.0** | |
| **diskcache** | 5.6.3 | 1 | Med (CVE-2025-69872) | *none* | **No fix** — triage/monitor |

All 22 are real. Critical headliners: **fastmcp → 3.x stable** and **authlib → 1.6.12+**.

### Workflow security
- **`evals.yaml` — CRITICAL by design.** `pull_request_target` (secret-bearing) + checkout of `pull_request.head.sha` (attacker-controlled) + `pytest` execution = secret-exfiltration footgun. The `paths-filter` is the trigger, not a mitigation. **Currently un-exploitable** (verified: 0 repo secrets, 0 env secrets, no org access) — but live the instant any secret is added. The `evals-and-secrets` environment has **0 protection rules** → gates nothing.
- **`build-and-publish` — LOW (well-built).** Push-to-main, version-bump-gated, **PyPI trusted publishing via OIDC** (no token). Correct pattern. (Caveat: no test gate — see Testing section.)
- **`security.yml` — GOOD.** Trivy + Semgrep from `cfdude/.github@main` (mutable ref — minor supply-chain note).
- **`ci.yaml` — GOOD.** `contents: read`, SHA-pinned, ruff + pytest 3.11/3.12.

### Committed secrets / exposure
**None.** `.env` untracked + never committed; `.env.sample` placeholder-only; secret-pattern scans found only doc stubs.

### Missing controls (public repo)
Dependabot alerts (disabled), Dependabot version updates (no config), secret scanning + push protection (disabled), CodeQL (mixed/broken state), Trivy (works but 22 unactioned).

### Remediation plan
**P0 — Critical:** (1) Neutralize the `evals.yaml` `pull_request_target` footgun **before** any secret is added — delete the workflow (eval suite is dead) or require maintainer-label + required-reviewer environment. (2) **Remove `evals-and-secrets` environment** (`gh api -X DELETE …/environments/evals-and-secrets`) + the `environment:` line. (3) Bump **fastmcp** off beta and **authlib** (`uv lock --upgrade-package …`).
**P1 — High:** (4) Upgrade the remaining CVE deps; triage `diskcache`. (5) Enable Dependabot + add `.github/dependabot.yml` (uv + github-actions ecosystems). (6) Enable secret scanning + push protection.
**P2 — Medium:** (7) Fix CodeQL state (enable default setup → auto-closes the 4 stale). (8) Pin the reusable `cfdude/.github@main` workflows to a SHA.

---

## Testing & CI/Build Health

### Coverage
227 tests collected; **223 passed, 4 deselected in 0.80s** (`-m "not e2e"`); only `test_e2e.py` is key-gated. **78% line coverage** (2131 stmts / 468 missed). Well-tested: `services.py` 92%, `clients.py` 75%, utils 91–100%, models 96–100%. **Blind spots:** `topics.py` **47%** (only 3 tests; the weakest real module — High), `data_models/charts.py` **0%** (likely dead — Medium), `servers/*` 37–67% (tool layer barely exercised — Medium/High). **No coverage gate** (pytest-cov installed but no `--cov` in CI/addopts — High).

### Markers/structure
Declared markers (`e2e`, `slow`, `integration`, `unit`) are mostly unused; **no test uses `integration` or `unit`**. `tests/test_integration.py` is **misnamed** — mocked unit test, no network, no marker. The marker taxonomy implies an integration tier that doesn't exist.

### Broken/orphaned
- **`evals/` non-functional → DELETE** (google-adk undeclared; outside testpaths; double-gated on key; CI "exit 5 = pass" confirms it never runs).
- **`functional_test.py`** is a manual `__main__` smoke script (no `test_*`, no asserts). Move to `scripts/smoke_stdio.py` or convert to a real `@pytest.mark.e2e` test. Don't leave a root-level `*_test.py` (latent glob footgun).

### CI issues

| Severity | Issue | Where | Fix |
|---|---|---|---|
| High | **No coverage gate.** | `ci.yaml:58`, `pyproject.toml:37,129` | `--cov=datacommons_mcp --cov-fail-under=75`. |
| High | **PyPI publish has NO test/lint gate** — version bump ships on any commit. | `build-and-publish*.yaml:67-72` | `needs: [ci-checks]` or inline lint+test before `uv build`. |
| High | **`evals.yaml` `pull_request_target` + untrusted checkout + secrets.** | `evals.yaml:7,45-49,78-79` | Delete (suite dead) or split trusted/untrusted jobs. |
| Medium | Matrix omits **3.13** though declared supported. | `ci.yaml:21` | Add `"3.13"`. |
| Medium | No type checking (mypy/pyright). | `ci.yaml:48-53` | Add `mypy`/`pyright` step + dev dep. |
| Medium | No dependency caching. | `ci.yaml:41-46` | `astral-sh/setup-uv` `enable-cache: true`. |
| Medium | Beta dep, unbounded. | `pyproject.toml:17` | Pin tested range. |
| Low | `paths-filter` can **skip tests** on `pyproject.toml`/`uv.lock`-only changes. | `ci.yaml:27-34,57` | Add those to filter or always run (suite <1s). |
| Low | No PR concurrency cancellation. | `ci.yaml` | Add `concurrency` block. |
| Low | `.mcpb` never built/validated in CI; committed `.mcpb` should be gitignored. | `build-extension.sh` | Add a pack/validate job on bundle changes. |

### Recommended testing + CI strategy
1. **Real 3-tier structure** (make the markers true): unit (default) / integration (`respx` HTTP tests) / e2e (key-gated, scheduled+dispatch only). CI default `pytest -m "not e2e"`.
2. **Coverage ratchet:** `--cov-fail-under=75` now; drive `topics.py` + `servers/*` up; raise to 85%.
3. **PR gate:** ruff format+lint → mypy → pytest+coverage → always-run tests; add 3.13 + uv caching.
4. **Gate before publish:** `build-and-publish` `needs:` CI; validate `.mcpb`.
5. **Type checking** added.
6. **Pre-commit hooks** (ruff format/check + fast pytest).
7. **Evals:** delete now; reintroduce later only as a separate optional-dependency group on manual/scheduled trigger — never a fork-PR gate.

---

## Dependencies & Packaging

### Dependency issues

| Severity | Dependency | Issue | Recommendation |
|----------|-----------|-------|----------------|
| High | `fastmcp>=3.0.0b1` | beta + unbounded; Critical CVE. | `fastmcp>=3.0.0,<4.0.0` (current 3.x stable); re-lock; test. |
| High | `fastapi>=0.100.0,<1.0.0` | **declared, never imported.** HTTP uses FastMCP's own stack. | Remove now; re-add when an actual FastAPI layer exists. |
| High | end-user `uv` requirement | `run_server.sh:32-38` hard-errors without `uv`; first launch needs network. | Acceptable for this team (IT deploys uv); ensure error links an installer. |
| Medium | `httpx>=0.24.0,<1.0.0` | **redundant direct decl** (no direct imports; transitive via fastmcp). | Remove direct decl. |
| Medium | `tiktoken>=0.5.0,<1.0.0` | **declared, never imported** (heavy Rust build). | Remove. |
| Medium | `click` (**missing**) | `cli.py:25` imports it but it's only transitive (via uvicorn). | **Add explicit + bounded.** |
| Medium | `requests` / `datacommons-client` / `pydantic-settings` | **no version bounds** (repro/supply-chain risk). | Add `>=X,<NEXT_MAJOR` bounds. |
| Low | `respx>=0.20.0` (dev) | **unused** (tests mock `requests` via `unittest.mock`). | Remove from dev extra. |
| Low | `cryptography>=46.0.5` | deliberate CVE over-pin of a transitive (`fastmcp→authlib→cryptography`). | Keep + document why; revisit after transitive bumps. |

### Packaging assessment
- **Flat layout (Medium):** package at repo root (`where=["."]`) risks importing in-tree source over the installed package; root is cluttered.
- **Build backend smell (Low):** `build-system.requires=["uv","setuptools"]` lists `uv` (not a backend) — clean to `["setuptools>=64"]`.
- **Dynamic version (good);** package-data ships topic JSONs (good); console script works only via transitive `click` (see gap).
- **Extension runtime-resolution (Medium):** shipping `pyproject.toml`+`uv.lock` + `uv run --frozen` is sound & small (~285 KB), BUT: requires `uv`+network on first launch; **dead `lib/` sys.path code in `run_server.py:26-34`** (old bundling model); **vestigial `manifest.json:16` `entry_point`** (live command is `bash run_server.sh`). Finish the migration: delete the dead code/comments.
- **Build cleanliness (Low):** stale `build/`, `*.egg-info/`, committed `.mcpb`, tracked `.DS_Store` — gitignore/clean.

### Recommended dependency / packaging strategy
- **Keep & bound:** fastmcp (stabilize), datacommons-client, requests, pydantic, pydantic-settings, python-dotenv, python-dateutil, cryptography (documented).
- **Add:** `click` (explicit + bounded).
- **Drop now:** `httpx` (redundant), `tiktoken` (unused), `fastapi` (unused today), `respx` (unused dev).
- **Do NOT add** SQLAlchemy/Alembic (no persistence). FastAPI only when HTTP API is built (vertical-slice: don't ship a framework around an empty center).
- **fastmcp:** never ship `>=3.0.0b1`; move to `>=3.x,<4` stable; treat as a release blocker for any "production" claim.
- **Constraint policy:** every direct dep gets `>=X,<NEXT_MAJOR`; keep committing `uv.lock`.
- **Build backend:** stay setuptools (clean the `requires`); hatchling/uv_build optional.
- **Layout:** migrate to `src/`; move stray root files out; gitignore build artifacts.
- **Extension:** commit to the `uv --frozen` model and delete the dead `lib/` code + fix manifest `entry_point`.

---

## Remediation Roadmap (proposed OpenSpec change decomposition)

The overhaul is too large for one spec. Decompose into sequenced OpenSpec changes, each going through the two-gate OpenSpec+Superpowers workflow (propose → Superpowers spec review → apply with TDD → Superpowers code review → docs → archive). Suggested order maximizes safety (security first) and minimizes rebase pain (cleanup before refactor before reorg):

1. **`security-hardening`** *(P0 — do first, mostly config/CI, low code risk)* — bump CVE deps (fastmcp→3.x stable, authlib, et al.) + re-lock; add `dependabot.yml`; enable secret scanning + push protection; fix/enable CodeQL (auto-close 4 stale); delete the `pull_request_target` footgun; remove the `evals-and-secrets` environment; gate PyPI publish on CI.
2. **`sever-upstream-deadweight`** *(High — pure deletion, unblocks everything)* — delete `evals/`, `examples/`, `evals.yaml`, `charts.py`, `functional_test.py` (or relocate), `SPRINT_2_INTEGRATION.md`; `git rm` tracked runtime CSV + gitignore; trim ADK/Gemini references from docs; drop unused deps (`fastapi`, `tiktoken`, `httpx`, `respx`); declare `click`; bound all deps.
3. **`unify-configuration`** *(High — low blast radius, high maintainability win)* — collapse `config.py` + `data_models/settings.py` + `settings.py` into one `Settings`; delete `_Compat*` + `get_output_settings()`; consolidate the test imports.
4. **`modularize-core`** *(Medium — the refactor)* — split `clients.py`, `services.py`, `topics.py`; reclassify `utils/` orchestrators into `services/`; adopt structured output + a single `ToolError` error model; clean the `places` contract.
5. **`src-layout-and-packaging`** *(Medium — mechanical reorg, do after splits settle)* — move to `src/`; rename `servers/`→`tools/`, `data_models/`→`models/`; clean build backend; finish the extension uv-migration (delete dead `lib/` code, fix manifest `entry_point`).
6. **`testing-and-ci-hardening`** *(High value, can parallel with 3–5)* — real unit/integration/e2e tiers; coverage gate (`--cov-fail-under=75`→85); mypy; 3.13 matrix; uv caching; pre-commit hooks; `.mcpb` CI validation.
7. **`docs-and-claude-code-tooling`** *(last)* — rewrite README; author a strong project `CLAUDE.md`; add Claude Code skills/agents/hooks/rules to enforce the new standards; archive all changes.

**Toolset confirmation:** Python ✓, pytest ✓, FastMCP ✓ (stabilize to 3.x), FastAPI — defer until a real HTTP layer exists, **SQLAlchemy/Alembic — not warranted** (no persistence; revisit only if persistent/multi-tenant state ever appears).

---

## Appendix — Premise corrections (for the record)
1. **No committed secrets / `.env`.** Only placeholder `.env.sample` is tracked.
2. **No duplicate `server.py`.** The entry chain is coherent; only a stale `.pyc` references a non-existent module.
3. **FastMCP fix is forward, not back.** 3.0 is GA (3.4.2); the runtime "pin < 3" warning is stale.
4. **The 4 CodeQL alerts are already fixed in code** — they linger only because CodeQL hasn't re-scanned.
5. **`_constrained_vars.py` and `date_utils.py` are live**, despite "temp"/utility naming.
