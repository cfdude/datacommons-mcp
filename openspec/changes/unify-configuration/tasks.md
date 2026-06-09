## 1. Consolidate config models into `config.py`

- [ ] 1.1 Move `DCSettingsSelector`, `DCSettings` (base), `BaseDCSettings`, `CustomDCSettings`, the `DCSettings` union, and `_parse_list_like_parameter` from `data_models/settings.py` into `config.py` (verbatim — preserve every field, default, validator, and the `compute_api_base_url` model_validator). Preserve the pre-existing `DCSettings` class-vs-union name rebinding as-is (do NOT "fix" it — that would be a behavior change / scope creep).
- [ ] 1.2 Add a single `get_dc_settings()` to `config.py` (the `DCSettingsSelector` → base/custom branch). Extend `config.py`'s `__all__` to export the moved DC symbols (`BaseDCSettings`, `CustomDCSettings`, `DCSettings`, `DCSettingsSelector`, `get_dc_settings`) so importers resolve cleanly.
- [ ] 1.3 Slim `AppConfig`: remove the dead DC-client fields (`dc_api_root`, `dc_search_root`, `dc_base_index`, `custom_dc_url`, `dc_custom_index`, `dc_search_scope`, `dc_topic_cache_paths`, `dc_root_topic_dcids`, `dc_base_root_topic_dcids`, `dc_use_search_indicators`), `safe_token_limit`, `assume_context_used`, and the `_CompatStorage`/`_CompatOutput` dataclasses + `.storage`/`.output` properties. Keep `dc_api_key`, `dc_type`, and the 7 output/storage fields + their validators. Update the `config.py` module/class docstrings, which currently advertise "flattened … with backward-compatible accessors", to reflect the slimmed model (no `_Compat*`).

## 2. Remove the dead output-settings path

- [ ] 2.1 Delete `OutputSettings` and `get_output_settings()` (incl. the dead `default_transport`/`sse_port` fields) from `data_models/settings.py`.
- [ ] 2.2 Remove `OutputHandlerConfig.from_settings()` and the production-unused `create_output_handler()` from `utils/output_handler.py`; keep `OutputHandlerConfig` itself and the explicit-config constructor path. **Also rewrite `OutputHandler.__init__` line ~112 from `config or OutputHandlerConfig.from_settings()` to `config or OutputHandlerConfig()`** (preserves the no-config path that the retained `test_init_with_default_config` relies on; `OutputHandlerConfig()` defaults `output_mode=AUTO`).
- [ ] 2.3 Remove `create_output_handler` from `datacommons_mcp/utils/__init__.py` (both the import block and `__all__`), since it's being deleted.
- [ ] 2.4 If `data_models/settings.py` now has no remaining live definitions, delete the file; otherwise leave only what's still used.

## 3. Repoint production imports + remove the shim

- [ ] 3.1 Update `servers/base.py` to import the DC union + `get_dc_settings` from `config.py` (replace `_get_dc_settings` with the consolidated `get_dc_settings`).
- [ ] 3.2 Update `clients.py` imports (`BaseDCSettings`/`CustomDCSettings`) to come from `config.py`.
- [ ] 3.3 Repoint the remaining `data_models.settings` / `settings.py` importers (verified full set): `utils/output_handler.py` (handled in 2.2), and the 5 test files (section 4). NOTE: `servers/observations.py` does NOT import these (it uses `get_config` from `common.py`, whose `AppConfig` import is `TYPE_CHECKING`-only and unaffected) — no edit needed there.
- [ ] 3.4 Delete `datacommons_mcp/settings.py` (the tests-only shim).
- [ ] 3.5 Import smoke: `uv run python -c "import datacommons_mcp.config; import datacommons_mcp.clients; import datacommons_mcp.servers.base"` succeeds (no circular import).

## 4. Migrate tests off deleted symbols

- [ ] 4.1 `test_settings.py` + `test_temp_constrained_vars.py`: repoint imports of `BaseDCSettings`/`CustomDCSettings`/`get_dc_settings`/`DCSettingsSelector` to `config.py`; keep all assertions.
- [ ] 4.2 `test_dc_client.py`: repoint `BaseDCSettings`/`CustomDCSettings` imports to `config.py`.
- [ ] 4.3 `test_output_handler.py`: **delete the 4 tests that exist solely to exercise the removed dead path** — `test_from_settings`, `test_create_output_handler_default_settings`, `test_create_output_handler_custom_settings`, `test_config_from_settings_includes_threshold` (their assertions are about the deleted env→settings→config path; retained output behavior stays covered by the lifespan-path tests here + `test_integration.py`). For any other test that uses `OutputSettings` incidentally, replace it with direct `OutputHandlerConfig(...)`. Net non-e2e count drops 228 → **224**.
- [ ] 4.4 `test_e2e.py`: replace `get_output_settings()` + `OutputHandlerConfig.from_settings(...)` with direct `OutputHandlerConfig(...)`; repoint `get_dc_settings` to `config.py`. (e2e is key-gated; verify it at least imports/collects.)

## 5. Verification & integration

- [ ] 5.1 Confirm zero readers remain for deleted symbols: `rg "OutputSettings|get_output_settings|from_settings|create_output_handler|_CompatStorage|_CompatOutput|datacommons_mcp.settings|from .settings import"` → only the consolidated/expected hits.
- [ ] 5.2 Behavior check: load base + custom settings with `DC_BASE_INDEX` unset and assert `base_uae_mem` vs `medium_ft`; assert computed `api_base_url`; assert `place_like_constraints` parsing — all unchanged.
- [ ] 5.3 Final gate: `uv run ruff format --check && uv run ruff check && uv run pytest -m "not e2e"` → **224 pass** (228 minus the 4 deleted dead-path tests; no OTHER drop); `uv lock --check` consistent; server boots via `python datacommons_mcp/run_server.py` (EOF) with both tools registered.
- [ ] 5.4 Commit per logical group (conventional commits), then proceed to Gate 2 (Superpowers code review) before finalizing.
