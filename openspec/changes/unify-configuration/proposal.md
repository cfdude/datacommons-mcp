## Why

Configuration is spread across three overlapping pydantic-settings sources that read the same `DC_*` env vars but feed different consumers, with a large amount of dead code accumulated from the fork:

- `config.py::AppConfig` — a flat model whose only live consumers read **7 output/storage fields** (the lifespan + `get_observations` each rebuild an `OutputHandlerConfig` from it). Its **11 DC-client fields, both `safe_token_limit`/`assume_context_used`, and the `_CompatStorage`/`_CompatOutput` accessors are all dead** (verified zero readers).
- `data_models/settings.py::OutputSettings` — **entirely dead in production** (the lifespan never uses it; it builds output config from `AppConfig`). Its `default_transport`/`sse_port` fields have **no reader anywhere**. It survives only because two test files import it.
- `data_models/settings.py::BaseDCSettings`/`CustomDCSettings` — a **legitimate discriminated union** (base vs custom DC, genuinely different fields and defaults) that drives `create_dc_client`. This is good design and is kept.
- `settings.py` — a **tests-only re-export shim** whose `get_dc_settings()` duplicates `base.py::_get_dc_settings()`.

This is change #3 of the overhaul. The goal is a **single, dead-code-free configuration module** — not a naive flatten-into-one-model (which would break a type-dependent default; see below).

## What Changes

- **Consolidate config into one module** (`config.py`) holding two clear concerns: the output/storage app config (slimmed `AppConfig`) and the DC connection settings (the base/custom discriminated union, moved out of `data_models/`).
- **Delete dead code:** `AppConfig`'s 11 unused DC-client fields, `safe_token_limit`, `assume_context_used`, and the `_CompatStorage`/`_CompatOutput` accessors; the `OutputSettings` model (incl. dead `default_transport`/`sse_port`) and `get_output_settings()`; the `OutputHandlerConfig.from_settings()` dead fallback and the never-called-in-prod `create_output_handler()`.
- **Remove the `settings.py` re-export shim**; keep one `get_dc_settings()` (the base/custom selector) as the single source.
- **Keep the DC discriminated union and `create_dc_client` unchanged** — preserving the type-dependent `DC_BASE_INDEX` default (`base_uae_mem` for base, `medium_ft` for custom), the computed `api_base_url`, and `place_like_constraints`.
- **Migrate the affected tests** (`test_settings.py`, `test_temp_constrained_vars.py`, `test_dc_client.py`, `test_output_handler.py`, `test_e2e.py`) to the consolidated module / to building output config directly, removing their dependence on the deleted `OutputSettings`/`get_output_settings`/`from_settings`/`create_output_handler` and the `settings.py` shim.

**BREAKING (internal only):** import paths for config symbols change; no MCP tool behavior, env-var names, or defaults change.

## Capabilities

### New Capabilities
- `unified-configuration`: a single configuration module is the source of truth — no duplicate or dead settings models, no backward-compat shims, no unused fields; the base/custom DC discriminated union is preserved with its type-dependent defaults; and all environment variables, defaults, and tool behavior are unchanged by the consolidation.

### Modified Capabilities
<!-- None — configuration was not covered by the existing dependency-security / supply-chain-scanning / ci-release-safety / lean-dependencies / repo-cleanliness specs. -->

## Impact

- **Code:** `config.py` (slim + absorb DC settings), delete `data_models/settings.py`'s dead `OutputSettings`/`get_output_settings` and relocate the DC union, delete `settings.py`, trim `utils/output_handler.py` (`from_settings`/`create_output_handler` + the `__init__` fallback) and `utils/__init__.py` (drop the `create_output_handler` re-export), update imports in `servers/base.py` and `clients.py`. (`servers/observations.py` needs no import change — it uses `get_config` from `common.py`.)
- **Tests:** migrate 5 test files off deleted symbols (no loss of coverage — same behaviors asserted against the consolidated module).
- **Risk:** medium-low. `create_dc_client` and the DC union are untouched, so the behavior-sensitive `base_index`/`api_base_url`/`place_like_constraints` logic is preserved by construction. The 228-test suite + server boot are the regression gate; the consolidation is behavior-preserving (all env aliases and defaults retained).
