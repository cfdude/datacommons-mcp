# Sprint 2: Integration - Data Commons MCP Server v1.2.0

**Date**: 2025-12-08
**Goal**: Wire infrastructure components into `get_observations` tool
**Prerequisite**: Sprint 1 complete (252 tests passing)

---

## Executive Summary

Sprint 1 built all infrastructure components (utilities, transports, multi-file export, lineage headers) but did not connect them to the actual MCP tool. This sprint completes the integration so that `get_observations` actually uses pagination streaming, output mode selection, and progress reporting.

---

## Sprint Backlog

### Phase 1: API Client Pagination (P0)

| ID | Story | Description | Acceptance Criteria |
|----|-------|-------------|---------------------|
| INT-001 | Add pagination to API client | Add `fetch_observations_page()` method to `clients.py` that accepts `page_token` parameter and returns response with `next_token` | Method exists, handles nextToken in request/response |
| INT-002 | Update observation response model | Ensure `observations.py` models support `next_token` field from API | Model parses nextToken correctly |

### Phase 2: Service Layer Integration (P0)

| ID | Story | Description | Acceptance Criteria |
|----|-------|-------------|---------------------|
| INT-003 | Integrate PaginationHandler into services | Update `get_observations_impl()` in `services.py` to use `PaginationHandler` for fetching | Pagination handler orchestrates multi-page fetches |
| INT-004 | Integrate OutputHandler into services | Use `OutputHandler` to decide screen vs file output based on pagination detection | Auto mode streams to file when nextToken present |
| INT-005 | Wire CSVStreamer for file output | Connect `CSVStreamer` to write observations during pagination | CSV files created with proper format and lineage |

### Phase 3: MCP Tool Interface (P0)

| ID | Story | Description | Acceptance Criteria |
|----|-------|-------------|---------------------|
| INT-006 | Add output params to get_observations | Add `output`, `output_format`, `multi_file` parameters to tool in `server.py` | Parameters accepted and passed to service layer |
| INT-007 | Update tool docstring | Update get_observations docstring to document new parameters and file output behavior | Docstring matches implementation plan |

### Phase 4: Progress & Transport (P1)

| ID | Story | Description | Acceptance Criteria |
|----|-------|-------------|---------------------|
| INT-008 | Wire transport progress callbacks | Pass transport's progress callback to PaginationHandler | Progress events emitted per page |
| INT-009 | Connect CLI transport to server | Ensure CLI's transport selection flows to get_observations | SSE transport streams progress to /events |

### Phase 5: Testing & Validation (P0)

| ID | Story | Description | Acceptance Criteria |
|----|-------|-------------|---------------------|
| INT-010 | Mock integration tests | Test full flow with mocked API responses (single page, multi-page, errors) | All scenarios pass |
| INT-011 | End-to-end test with real API | Test against live Data Commons API with known large dataset | File created, rows match expected |
| INT-012 | Regression tests | Ensure existing behavior unchanged for small datasets | All 252 existing tests still pass |

---

## Technical Design

### 1. clients.py Changes

```python
# Add to DataCommonsClient class

async def fetch_observations_page(
    self,
    variable_dcid: str,
    place_dcid: str,
    child_place_type: str | None = None,
    date: str = "latest",
    date_range_start: str | None = None,
    date_range_end: str | None = None,
    page_token: str | None = None,
) -> tuple[dict, str | None]:
    """
    Fetch a single page of observations.

    Returns:
        Tuple of (response_data, next_token)
        next_token is None if no more pages
    """
    payload = {
        "variable": {"dcids": [variable_dcid]},
        "entity": {"dcids": [place_dcid]},
    }

    if child_place_type:
        payload["entity"] = {
            "expression": f"linkedEntities({place_dcid}, containedInPlace+, typeOf, {child_place_type})"
        }

    if page_token:
        payload["pageToken"] = page_token

    # ... date handling ...

    response = await self._post("/v2/observation", payload)
    next_token = response.get("nextToken")

    return response, next_token
```

### 2. services.py Integration

```python
from datacommons_mcp.utils import (
    PaginationHandler,
    OutputHandler,
    CSVStreamer,
    PathResolver,
    create_transport,
)

async def get_observations_impl(
    variable_dcid: str,
    place_dcid: str,
    child_place_type: str | None = None,
    # ... existing params ...
    output: Literal["auto", "screen", "file"] = "auto",
    output_format: Literal["csv", "json"] = "csv",
    multi_file: bool = False,
    transport: Transport | None = None,
) -> dict:
    """Enhanced get_observations with pagination streaming."""

    # Initialize utilities
    path_resolver = PathResolver()
    csv_streamer = CSVStreamer(path_resolver)

    # Create pagination handler
    pagination_handler = PaginationHandler(
        client=client,
        csv_streamer=csv_streamer,
        progress_callback=transport.create_progress_callback() if transport else None,
    )

    # Fetch with auto-streaming
    result = await pagination_handler.fetch_with_auto_streaming(
        variable_dcid=variable_dcid,
        place_dcid=place_dcid,
        child_place_type=child_place_type,
        # ... other params ...
        output_mode=output,
    )

    # Handle multi-file export if requested
    if multi_file and result.get("output_mode") == "file":
        # Generate companion files
        pass

    return result
```

### 3. server.py Tool Update

```python
@mcp.tool()
async def get_observations(
    variable_dcid: str,
    place_dcid: str,
    child_place_type: str | None = None,
    source_override: str | None = None,
    date: str = "latest",
    date_range_start: str | None = None,
    date_range_end: str | None = None,
    # NEW parameters
    output: Literal["auto", "screen", "file"] = "auto",
    output_format: Literal["csv", "json"] = "csv",
    multi_file: bool = False,
) -> dict:
    """
    Fetches observations for a statistical variable from Data Commons.

    ... existing docstring ...

    Args:
        output: Output mode - 'auto' (default), 'screen', or 'file'.
            Auto mode detects large datasets and streams to file.
        output_format: Output format for file mode - 'csv' (default) or 'json'.
        multi_file: If True, creates companion files with place and source metadata.

    Returns:
        For screen mode:
        - output_mode: "screen"
        - data: The observation data

        For file mode:
        - output_mode: "file"
        - file_path: Path to the created CSV/JSON file
        - rows_written: Number of data rows written
        - pages_fetched: Number of API pages fetched
        - file_size_bytes: Size of the output file
    """
```

---

## File Changes Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `clients.py` | Modify | Add `fetch_observations_page()` method |
| `data_models/observations.py` | Modify | Add `next_token` field support |
| `services.py` | Modify | Integrate PaginationHandler, OutputHandler, CSVStreamer |
| `server.py` | Modify | Add output params to get_observations tool |
| `tests/test_integration.py` | Create | Mock integration tests |
| `tests/test_e2e.py` | Create | End-to-end tests with real API |

---

## Test Scenarios

### Mock Integration Tests

```python
# test_integration.py

class TestPaginationIntegration:
    """Test pagination flow with mocked API."""

    async def test_single_page_returns_screen(self):
        """Single page response returns to screen."""
        # Mock API returns no nextToken
        # Assert output_mode == "screen"

    async def test_multi_page_streams_to_file(self):
        """Multi-page response streams to CSV."""
        # Mock API returns nextToken on first 2 pages
        # Assert output_mode == "file"
        # Assert file exists with correct row count

    async def test_output_file_forces_file_mode(self):
        """output='file' always creates file."""
        # Even single-page response
        # Assert output_mode == "file"

    async def test_output_screen_returns_directly(self):
        """output='screen' returns data directly."""
        # Even if multi-page, returns truncated
        # Assert output_mode == "screen"

    async def test_progress_callback_called(self):
        """Progress callback called per page."""
        # Mock transport with callback
        # Assert callback called N times for N pages

    async def test_lineage_headers_in_csv(self):
        """CSV includes lineage headers."""
        # Parse output file
        # Assert headers present

    async def test_multi_file_creates_companions(self):
        """multi_file=True creates place/source files."""
        # Assert companion files exist
```

### End-to-End Tests

```python
# test_e2e.py

@pytest.mark.e2e
@pytest.mark.skipif(not os.getenv("DC_API_KEY"), reason="No API key")
class TestEndToEnd:
    """Real API tests (require DC_API_KEY)."""

    async def test_us_counties_population(self):
        """Fetch all US county population - known large dataset."""
        result = await get_observations(
            variable_dcid="Count_Person",
            place_dcid="country/USA",
            child_place_type="County",
            date="2020",
            output="auto",
        )
        assert result["output_mode"] == "file"
        assert result["rows_written"] > 3000  # ~3,143 US counties
        assert Path(result["file_path"]).exists()

    async def test_single_state_returns_screen(self):
        """Single state query returns to screen."""
        result = await get_observations(
            variable_dcid="Count_Person",
            place_dcid="geoId/06",  # California
            date="latest",
            output="auto",
        )
        assert result["output_mode"] == "screen"
```

---

## Success Criteria

| Metric | Target |
|--------|--------|
| All existing tests pass | 252/252 |
| New integration tests pass | 100% |
| US counties query streams to file | Yes |
| Single state returns to screen | Yes |
| Progress callback fires per page | Yes |
| CSV lineage headers present | Yes |
| Multi-file export works | Yes |

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| API pagination format differs from docs | Add response format validation, fail fast with clear error |
| Large dataset timeout | Implement configurable page timeout, retry logic |
| File permission errors | PathResolver validates write access at startup |
| Memory spike during CSV write | CSVStreamer uses buffered writes, flush per page |

---

## Sprint Execution Order

1. **INT-001, INT-002**: API client pagination (foundation)
2. **INT-003, INT-004, INT-005**: Service layer integration (core logic)
3. **INT-006, INT-007**: MCP tool interface (user-facing)
4. **INT-010, INT-012**: Mock tests + regression (validation)
5. **INT-008, INT-009**: Progress transport (enhancement)
6. **INT-011**: E2E test (final validation)

---

## Definition of Done

- [ ] All 12 stories complete
- [ ] All tests pass (existing + new)
- [ ] `output="auto"` streams large datasets to file
- [ ] `output="file"` always creates file
- [ ] `output="screen"` always returns data directly
- [ ] Progress callbacks work with SSE transport
- [ ] CSV files include lineage headers
- [ ] Multi-file export creates companion files
- [ ] README accurately describes working features
- [ ] Version remains 1.2.0 (features now match docs)
