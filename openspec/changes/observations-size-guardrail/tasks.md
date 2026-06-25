## 1. Config + exception + boundary

- [ ] 1.1 `config.py`: add `max_places: int = Field(default=1000, alias="DC_MAX_PLACES", ge=1, le=100000, description=...)` to `AppConfig`.
- [ ] 1.2 `exceptions.py`: add `class ResultTooLargeError(_ErrorStrMixin, ValueError)` (mirror `InvalidInputError`).
- [ ] 1.3 `servers/common.py`: add `ResultTooLargeError` to the `_CLIENT_FACING_ERRORS` tuple so `tool_error_boundary` surfaces its message (not masked).

## 2. Cheap child-place count

- [ ] 2.1 `clients/entities.py`: add `async def count_child_places(self, parent_place_dcid: str, child_place_type: str) -> int` wrapping `self.dc.node.fetch_place_children(place_dcids=parent_place_dcid, children_type=child_place_type, as_dict=True)` → `len(response.get(parent_place_dcid, []))` (mirror `child_place_type_exists`).

## 3. The guardrail (service, pre-fetch)

- [ ] 3.1 `services/observations.py::get_observations_paginated`: add a `max_places: int | None = None` parameter. After the request is built (so `request.place_dcid` is the RESOLVED parent) and BEFORE `fetch_obs_page`, when `request.child_place_type` and `max_places` are set: `n = await client.count_child_places(request.place_dcid, request.child_place_type)`; if `n > max_places`, raise `ResultTooLargeError` with an actionable message — the count `n`, the `child_place_type`, the parent, `DC_MAX_PLACES={max_places}`, and guidance (narrow by date/place type/fewer places, or streaming coming). Single-place queries (no `child_place_type`) skip the check.
- [ ] 3.2 `servers/observations.py::get_observations`: pass `max_places=config.max_places` (from `get_config(ctx)`) into the service call, inside the existing `tool_error_boundary()`.

## 4. Tests

- [ ] 4.1 `tests/test_services.py`: child-place query where `mock_client.count_child_places` returns `> max_places` → `pytest.raises(ResultTooLargeError)`, before any `fetch_obs`. Returns `<= max_places` → proceeds normally (existing flow). A single-place query (no `child_place_type`) → `count_child_places` NOT called, proceeds.
- [ ] 4.2 `tests/test_dc_client.py`: `count_child_places` returns `len` of the children for the parent (mock `fetch_place_children`).
- [ ] 4.3 `tests/test_error_boundary.py` (or `test_structured_output.py` Client(mcp)): a `get_observations` call that trips the guardrail surfaces an actionable `ToolError` (message contains the limit/guidance), not the generic masked message. (Mock the service or `count_child_places` to force the over-limit path; set a small `DC_MAX_PLACES`.)
- [ ] 4.4 Confirm existing `TestGetObservations` tests still pass (they use single-place or small child queries; the new param defaults to gating only when both set).

## 5. Docs + verification

- [ ] 5.1 `docs/reference.md`: note the place-count limit + `DC_MAX_PLACES` (and that very large geographies are refused with guidance until streaming lands).
- [ ] 5.2 `uv run --extra dev ruff format --check && ruff check && mypy src/datacommons_mcp && pytest -m "not e2e" --cov=datacommons_mcp --cov-fail-under=80` → all pass; `uv lock --check`.
- [ ] 5.3 Commit per logical group; Gate 2 before docs/archive.
