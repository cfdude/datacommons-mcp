"""Tests for typed structured output of the MCP tools (slice 4d).

Pins the contract that both tools advertise field-level output schemas (not the old
``{"type": "object", "additionalProperties": true}``) and that returned structured
content matches the typed models.
"""

import pytest

from datacommons_mcp.data_models.observations import (
    FacetMetadata,
    Node,
    ObservationRequest,
    ObservationToolResponse,
    PlaceObservation,
)
from datacommons_mcp.data_models.search import SearchResponse, SearchVariable


@pytest.fixture
def _dc_env(monkeypatch):
    monkeypatch.setenv("DC_API_KEY", "test-key")
    monkeypatch.delenv("DC_TYPE", raising=False)


def _is_structureless(schema: dict | None) -> bool:
    """True if the schema is the useless open-object schema (no field-level structure)."""
    if not schema:
        return True
    return not (schema.get("properties") or schema.get("anyOf") or schema.get("$defs"))


@pytest.mark.asyncio
async def test_both_tools_advertise_field_level_output_schema(_dc_env):
    from fastmcp import Client

    from datacommons_mcp.fastmcp_server import mcp

    async with Client(mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}

    # Neither tool should advertise the old {"additionalProperties": true} open object.
    assert not _is_structureless(tools["search_indicators"].outputSchema)
    assert not _is_structureless(tools["get_observations"].outputSchema)

    # get_observations should expose BOTH branches (screen/file) in its schema,
    # via the output_mode literal tags (asserted specifically, not as loose substrings).
    obs_schema_text = str(tools["get_observations"].outputSchema)
    assert "'screen'" in obs_schema_text  # output_mode const for the screen branch
    assert "'file'" in obs_schema_text  # output_mode const for the file branch


@pytest.mark.asyncio
async def test_search_indicators_structured_content_matches_model(monkeypatch, _dc_env):
    from fastmcp import Client

    import datacommons_mcp.tools.search as search_mod
    from datacommons_mcp.fastmcp_server import mcp

    async def _fake_search(*args, **kwargs):
        return SearchResponse(
            status="SUCCESS",
            dcid_name_mappings={"Count_Person": "Population"},
            variables=[SearchVariable(dcid="Count_Person")],
        )

    monkeypatch.setattr(search_mod, "search_indicators_service", _fake_search)

    async with Client(mcp) as client:
        result = await client.call_tool("search_indicators", {"query": "population"})

    # SearchResponse is a single (non-union) model -> flat structured content.
    sc = result.structured_content
    assert sc["status"] == "SUCCESS"
    assert sc["variables"][0]["dcid"] == "Count_Person"


@pytest.mark.asyncio
async def test_get_observations_screen_structured_content(monkeypatch, _dc_env):
    from fastmcp import Client

    import datacommons_mcp.tools.observations as obs_mod
    from datacommons_mcp.fastmcp_server import mcp

    response = ObservationToolResponse(
        variable=Node(dcid="Count_Person", name="Population"),
        place_observations=[],
        source_metadata=FacetMetadata(source_id="census_pop"),
    )
    request = ObservationRequest(variable_dcid="Count_Person", place_dcid="geoId/06")

    async def _fake_obs(*args, **kwargs):
        return response, request, None  # (response, request, next_token=None)

    monkeypatch.setattr(obs_mod, "get_observations_service", _fake_obs)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_observations",
            {"variable_dcid": "Count_Person", "place_dcid": "geoId/06", "output": "screen"},
        )

    # get_observations returns a tagged union -> FastMCP nests it under "result".
    # Pin that wrapper explicitly (do not tolerate a flat shape).
    sc = result.structured_content
    assert "result" in sc
    payload = sc["result"]
    assert payload["output_mode"] == "screen"
    assert payload["data"]["variable"]["dcid"] == "Count_Person"


@pytest.mark.asyncio
async def test_get_observations_file_structured_content_has_preview(monkeypatch, tmp_path, _dc_env):
    """File-mode result carries the bounded preview + summary metadata in structured output."""
    from fastmcp import Client

    import datacommons_mcp.tools.observations as obs_mod
    from datacommons_mcp.fastmcp_server import mcp

    # Write exports to a temp dir, not the user's ~/Documents.
    monkeypatch.setenv("DC_STORAGE_DIR", str(tmp_path))

    response = ObservationToolResponse(
        variable=Node(dcid="Count_Person", name="Population"),
        place_observations=[
            PlaceObservation(
                place=Node(dcid="geoId/06", name="California", type_of=["State"]),
                time_series=[("2020-01-01", 39.5), ("2021-01-01", 39.2)],
            )
        ],
        source_metadata=FacetMetadata(source_id="census_pop"),
    )
    request = ObservationRequest(variable_dcid="Count_Person", place_dcid="geoId/06")

    async def _fake_obs(*args, **kwargs):
        return response, request, None

    monkeypatch.setattr(obs_mod, "get_observations_service", _fake_obs)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_observations",
            {"variable_dcid": "Count_Person", "place_dcid": "geoId/06", "output": "file"},
        )

    payload = result.structured_content["result"]
    assert payload["output_mode"] == "file"
    assert payload["preview"], "file result should carry a non-empty preview"
    assert payload["preview"][0]["variable_name"] == "Population"
    assert payload["columns"]
    assert str(payload["rows_written"]) in payload["summary"]
