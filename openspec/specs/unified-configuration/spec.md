# unified-configuration Specification

## Purpose
TBD - created by archiving change unify-configuration. Update Purpose after archive.
## Requirements
### Requirement: A single module is the source of truth for configuration
Configuration models SHALL live in one module. There SHALL be no separate re-export shim and no parallel settings module duplicating configuration logic.

#### Scenario: The settings shim is removed
- **WHEN** the source tree is inspected
- **THEN** `datacommons_mcp/settings.py` no longer exists, and the `get_dc_settings()` selector logic exists in exactly one place

#### Scenario: Config symbols import from one module
- **WHEN** production code and tests import configuration models (app/output config and the DC settings union)
- **THEN** they import them from the single consolidated configuration module, not from two different modules

### Requirement: No dead configuration code
The configuration surface SHALL contain no unused models, fields, or backward-compatibility accessors.

#### Scenario: Backward-compat accessors removed
- **WHEN** `config.py` is inspected
- **THEN** the `_CompatStorage` / `_CompatOutput` dataclasses and the `.storage` / `.output` accessor properties are absent (verified to have zero readers)

#### Scenario: Unused app-config fields removed
- **WHEN** the slimmed app/output config model is inspected
- **THEN** it no longer declares the DC-client fields that the DC settings union owns, nor `safe_token_limit` / `assume_context_used` (all verified to have zero readers)

#### Scenario: Dead output settings removed
- **WHEN** the source tree is inspected
- **THEN** the `OutputSettings` model, `get_output_settings()`, the `OutputHandlerConfig.from_settings()` fallback, and the production-unused `create_output_handler()` are absent, and `default_transport` / `sse_port` exist nowhere

### Requirement: The base/custom DC settings union is preserved with type-dependent defaults
The discriminated base/custom DC settings (driving `create_dc_client`) SHALL be retained, including its type-dependent defaults — consolidation MUST NOT flatten it into a single model in a way that changes a default.

#### Scenario: Type-dependent DC_BASE_INDEX default preserved
- **WHEN** base and custom DC settings are loaded with `DC_BASE_INDEX` unset
- **THEN** the base setting resolves `base_index` to `"base_uae_mem"` and the custom setting resolves it to `"medium_ft"` (each unchanged from before)

#### Scenario: Computed custom api_base_url preserved
- **WHEN** custom DC settings are loaded with `CUSTOM_DC_URL` set and `DC_API_BASE_URL` unset
- **THEN** `api_base_url` is computed as `<custom_dc_url rstrip '/'> + "/core/api/v2/"` (unchanged)

#### Scenario: place_like_constraints preserved
- **WHEN** custom DC settings are loaded with `PLACE_LIKE_CONSTRAINTS` set
- **THEN** the value is parsed and reaches the custom client exactly as before

### Requirement: Configuration consolidation is behavior-preserving
All environment-variable names, defaults, validation, and resulting MCP tool behavior SHALL be unchanged by the consolidation.

#### Scenario: Env aliases and defaults unchanged
- **WHEN** the consolidated config is loaded from the same environment as before
- **THEN** every env-var alias (`DC_API_KEY`, `DC_TYPE`, `DC_STORAGE_DIR`, `DC_SCREEN_ROW_THRESHOLD`, `DC_OUTPUT_FORMAT`, `DC_MAX_PAGES`, etc.) and its default value resolve to the same effective configuration as before

#### Scenario: Suite and server stay green
- **WHEN** the full non-e2e test suite runs and the stdio server is booted after consolidation
- **THEN** all non-e2e tests pass and the server starts and registers both tools without error

#### Scenario: Tests are migrated without losing coverage of retained behavior
- **WHEN** the tests that previously imported `OutputSettings` / `get_output_settings` / `get_dc_settings` (from the shim) / `from_settings` / `create_output_handler` are reconciled after migration
- **THEN** tests of RETAINED behavior are repointed at the consolidated module and keep their assertions, and tests whose ONLY subject was the removed dead path (the env→`OutputSettings`→`from_settings`/`create_output_handler` flow) are removed — leaving no test importing a deleted symbol and no loss of coverage for any behavior that still exists

