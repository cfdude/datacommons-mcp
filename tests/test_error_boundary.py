"""Tests for the consistent error model (tool_error_boundary + masking)."""

import pytest
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, ValidationError

from datacommons_mcp.exceptions import (
    DataLookupError,
    InvalidDateFormatError,
    InvalidDateRangeError,
    InvalidInputError,
    NoDataFoundError,
    ResultTooLargeError,
)
from datacommons_mcp.tools.common import _GENERIC_ERROR_MESSAGE, tool_error_boundary

# --- Unit tests: the context manager mapping ---


@pytest.mark.parametrize(
    "exc_cls",
    [
        InvalidInputError,
        DataLookupError,
        NoDataFoundError,
        InvalidDateFormatError,
        InvalidDateRangeError,
        ResultTooLargeError,
    ],
)
def test_domain_exception_becomes_tool_error_with_message(exc_cls):
    with pytest.raises(ToolError) as ei, tool_error_boundary():
        raise exc_cls("actionable detail")
    assert "actionable detail" in str(ei.value)
    assert isinstance(ei.value.__cause__, exc_cls)


def test_pydantic_validation_error_is_masked():
    class _M(BaseModel):
        x: int

    with pytest.raises(ToolError) as ei, tool_error_boundary():
        _M(x="not-an-int")  # raises ValidationError (a ValueError subclass)
    assert str(ei.value) == _GENERIC_ERROR_MESSAGE
    assert isinstance(ei.value.__cause__, ValidationError)


def test_keyerror_is_masked_no_leak():
    with pytest.raises(ToolError) as ei, tool_error_boundary():
        {}["secret-internal-key"]  # KeyError is a LookupError subclass
    msg = str(ei.value)
    assert msg == _GENERIC_ERROR_MESSAGE
    assert "secret-internal-key" not in msg
    assert isinstance(ei.value.__cause__, KeyError)


def test_indexerror_is_masked_no_leak():
    with pytest.raises(ToolError) as ei, tool_error_boundary():
        [][99]  # IndexError is a LookupError subclass
    assert str(ei.value) == _GENERIC_ERROR_MESSAGE
    assert isinstance(ei.value.__cause__, IndexError)


def test_unexpected_error_is_masked_no_leak():
    with pytest.raises(ToolError) as ei, tool_error_boundary():
        raise RuntimeError("internal secret detail")
    assert str(ei.value) == _GENERIC_ERROR_MESSAGE
    assert "internal secret detail" not in str(ei.value)


def test_existing_tool_error_passes_through_unchanged():
    original = ToolError("already a tool error")
    with pytest.raises(ToolError) as ei, tool_error_boundary():
        raise original
    assert ei.value is original  # not re-wrapped


# --- Integration tests: through an in-memory FastMCP client ---


@pytest.fixture
def _dc_env(monkeypatch):
    monkeypatch.setenv("DC_API_KEY", "test-key")
    monkeypatch.delenv("DC_TYPE", raising=False)


@pytest.mark.asyncio
async def test_invalid_input_surfaces_actionable_message_to_client(_dc_env):
    from fastmcp import Client

    from datacommons_mcp.fastmcp_server import mcp  # registers the tools on import

    async with Client(mcp) as client:
        with pytest.raises(ToolError) as ei:
            await client.call_tool(
                "get_observations",
                {"variable_dcid": "", "place_dcid": "geoId/06"},
            )
    assert "variable_dcid" in str(ei.value)


@pytest.mark.asyncio
async def test_unexpected_error_is_masked_to_client(monkeypatch, _dc_env):
    from fastmcp import Client

    from datacommons_mcp.fastmcp_server import mcp  # registers the tools on import

    async def _boom(*args, **kwargs):
        raise RuntimeError("internal detail xyz")

    monkeypatch.setattr("datacommons_mcp.services.observations.get_observations_paginated", _boom)

    async with Client(mcp) as client:
        with pytest.raises(ToolError) as ei:
            await client.call_tool(
                "get_observations",
                {"variable_dcid": "Count_Person", "place_dcid": "geoId/06"},
            )
    assert "internal detail xyz" not in str(ei.value)
    assert str(ei.value) == _GENERIC_ERROR_MESSAGE  # masked to the generic message, not empty/other
