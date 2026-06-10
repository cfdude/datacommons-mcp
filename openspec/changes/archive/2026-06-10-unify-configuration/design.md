## Context

A read-only consumer-graph audit established the real shape of the three config sources (more nuanced than the forensic summary): `AppConfig` is live only for 7 output/storage fields; `OutputSettings` + `default_transport`/`sse_port` are dead in production; the `BaseDCSettings`/`CustomDCSettings` discriminated union is live and drives `create_dc_client`; `settings.py` is a tests-only shim. The base/custom split carries behavior-sensitive, type-dependent defaults (`DC_BASE_INDEX` → `base_uae_mem` vs `medium_ft`), a computed `api_base_url`, and `place_like_constraints`.

## Goals / Non-Goals

**Goals:**
- One configuration module, zero dead/duplicate config code, no shims.
- Preserve all env aliases, defaults, validation, and tool behavior (behavior-preserving refactor).

**Non-Goals:**
- No `create_dc_client`/client refactor (that's #4); no `src/` layout (#5).
- No removal of `place_like_constraints` (it dies with the search-vector migration in #4).
- No change to env-var names or defaults.

## Decisions

**1. Keep the base/custom discriminated union; do NOT flatten into one model.** The audit proved `DC_BASE_INDEX`'s default is type-dependent and the custom model has a computed `api_base_url` + `place_like_constraints`. A single flat model cannot express a type-dependent default cleanly and would risk silently changing it. *Alternative (one flat AppConfig-style model for everything):* rejected — it's what created the drift, and it can't preserve the base/custom default split. "Single source of truth" is achieved by removing **duplication and dead code**, not by collapsing two legitimately-different concerns into one model.

**2. One module = `config.py`.** Move `BaseDCSettings`/`CustomDCSettings`/`DCSettingsSelector` and the single `get_dc_settings()` selector into `config.py`; delete `data_models/settings.py` and `settings.py`. `config.py` ends up holding: the slimmed app/output config + the DC settings union + the selector. *Alternative (a `config/` package):* deferred to the `src/` reorg in #5 — avoid churn now.

**3. Slim `AppConfig` to its live output/storage role.** Remove its 11 dead DC-client fields, `safe_token_limit`, `assume_context_used`, and the `_Compat*` accessors. Keep the 7 fields the lifespan + `get_observations` actually read (storage_directory, output_format, multi_file_export, include_lineage, max_pages, screen_row_threshold) plus `dc_type` (log) and the required `dc_api_key`. Keep the name `AppConfig` to minimize churn.

**4. Delete the dead output path and migrate its tests.** Remove `OutputSettings`, `get_output_settings()`, `OutputHandlerConfig.from_settings()`, and `create_output_handler()`. The two tests that use them (`test_output_handler.py`, `test_e2e.py`) are migrated to build `OutputHandlerConfig` directly (exactly as production does in `base.py`/`observations.py`), preserving every assertion. `test_settings.py`/`test_temp_constrained_vars.py`/`test_dc_client.py` only need their import paths repointed at `config.py`.

**5. One `get_dc_settings()`.** Collapse `settings.py::get_dc_settings` and `base.py::_get_dc_settings` into a single function in `config.py`; `base.py` calls it.

## Risks / Trade-offs

- **A behavior-sensitive default changes** → Mitigation: the union is kept verbatim, so `base_index`/`api_base_url`/`place_like_constraints` are preserved by construction; `test_settings.py` already locks these defaults and must stay green.
- **Test migration drops a real assertion** → Mitigation: migrate behavior-tests by repointing imports + replacing `from_settings(OutputSettings(...))` with direct `OutputHandlerConfig(...)` using the same values. The 4 tests that exist *only* to exercise the removed dead path (`test_from_settings`, `test_create_output_handler_default_settings`, `test_create_output_handler_custom_settings`, `test_config_from_settings_includes_threshold`) are deleted — their subject no longer exists, and retained output behavior stays covered by the lifespan-path tests + `test_integration.py`. Net non-e2e count: **228 → 224**, with no other assertion lost.
- **`api_key` is required-but-unused on `CustomDCSettings`** → leave as-is (preserving current behavior; tightening it is out of scope).
- **Circular import risk** moving the DC union into `config.py` (it imports `SearchScope` from `data_models/enums.py`, which is fine; `clients.py` will import the union from `config.py`) → Mitigation: `enums.py` has no config deps, so no cycle; verify with an import smoke.

## Migration Plan

1. Move the DC union + selector + `get_dc_settings` into `config.py`; slim `AppConfig`; delete `_Compat*`.
2. Delete `OutputSettings`/`get_output_settings`; trim `output_handler.py` (`from_settings`/`create_output_handler`).
3. Repoint imports in `base.py`, `clients.py`, `observations.py`; delete `settings.py` and the dead bits of `data_models/settings.py` (the file may be removed if nothing else remains).
4. Migrate the 5 test files; run `ruff` + full non-e2e suite + server boot.

**Rollback:** revert the change's commits; no data/migration involved.
