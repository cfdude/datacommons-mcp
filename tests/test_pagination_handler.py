# Copyright 2025 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Tests for the pagination handler utility."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from datacommons_mcp.data_models.observations import (
    FacetMetadata,
    Node,
    ObservationRequest,
    ObservationToolResponse,
    PlaceObservation,
)
from datacommons_mcp.utils.pagination_handler import (
    OutputMode,
    PaginationHandler,
    PaginationResult,
)
from datacommons_mcp.utils.path_resolver import PathResolver


@pytest.fixture
def temp_storage():
    """Create a temporary storage directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def path_resolver(temp_storage):
    """Create a PathResolver with temporary storage."""
    return PathResolver(temp_storage)


@pytest.fixture
def mock_client():
    """Create a mock DCClient."""
    client = MagicMock()
    client.fetch_obs_page = AsyncMock()
    return client


@pytest.fixture
def sample_request():
    """Create a sample ObservationRequest."""
    return ObservationRequest(
        variable_dcid="Count_Person",
        place_dcid="country/USA",
        child_place_type="State",
    )


@pytest.fixture
def sample_response():
    """Create a sample ObservationToolResponse."""
    return ObservationToolResponse(
        variable=Node(dcid="Count_Person", name="Population"),
        place_observations=[
            PlaceObservation(
                place=Node(dcid="geoId/06", name="California", type_of=["State"]),
                time_series=[
                    ("2020-01-01", 39538223.0),
                    ("2021-01-01", 39237836.0),
                ],
            ),
        ],
        source_metadata=FacetMetadata(source_id="census_pop"),
        alternative_sources=[],
    )


class TestOutputMode:
    """Tests for OutputMode enum."""

    def test_output_mode_values(self):
        """Test OutputMode enum values."""
        assert OutputMode.SCREEN.value == "screen"
        assert OutputMode.FILE.value == "file"


class TestPaginationResult:
    """Tests for PaginationResult dataclass."""

    def test_screen_mode_result(self, sample_response):
        """Test PaginationResult for screen mode."""
        result = PaginationResult(
            output_mode=OutputMode.SCREEN,
            response=sample_response,
            pages_fetched=1,
        )

        result_dict = result.to_dict()
        assert result_dict["output_mode"] == "screen"
        assert "data" in result_dict
        assert result_dict["data"]["variable"]["dcid"] == "Count_Person"

    def test_file_mode_result(self, temp_storage):
        """Test PaginationResult for file mode."""
        file_path = temp_storage / "test.csv"
        result = PaginationResult(
            output_mode=OutputMode.FILE,
            file_path=file_path,
            rows_written=100,
            pages_fetched=5,
            file_size_bytes=1024,
            unique_places={"geoId/06", "geoId/48"},
        )

        result_dict = result.to_dict()
        assert result_dict["output_mode"] == "file"
        assert result_dict["file_path"] == str(file_path)
        assert result_dict["rows_written"] == 100
        assert result_dict["pages_fetched"] == 5
        assert result_dict["file_size_bytes"] == 1024
        assert result_dict["unique_places_count"] == 2

    def test_file_mode_with_companion_files(self, temp_storage):
        """Test PaginationResult with companion files."""
        result = PaginationResult(
            output_mode=OutputMode.FILE,
            file_path=temp_storage / "observations.csv",
            rows_written=100,
            pages_fetched=1,
            file_size_bytes=1024,
            companion_files={
                "places": temp_storage / "observations.places.csv",
                "sources": temp_storage / "observations.sources.csv",
            },
        )

        result_dict = result.to_dict()
        assert "companion_files" in result_dict
        assert "places" in result_dict["companion_files"]
        assert "sources" in result_dict["companion_files"]


class TestPaginationHandler:
    """Tests for PaginationHandler class."""

    def test_init(self, mock_client, path_resolver):
        """Test PaginationHandler initialization."""
        handler = PaginationHandler(
            mock_client,
            path_resolver,
            max_pages=50,
            include_lineage=True,
        )

        assert handler.client == mock_client
        assert handler.path_resolver == path_resolver
        assert handler.max_pages == 50
        assert handler.include_lineage is True

    @pytest.mark.asyncio
    async def test_single_page_returns_screen_mode(
        self, mock_client, path_resolver, sample_request, sample_response
    ):
        """Test that single-page responses return screen mode."""
        handler = PaginationHandler(mock_client, path_resolver)

        result = await handler.fetch_with_auto_streaming(
            request=sample_request,
            processed_first_response=sample_response,
            first_page_next_token=None,  # No more pages
        )

        assert result.output_mode == OutputMode.SCREEN
        assert result.response == sample_response
        assert result.pages_fetched == 1
        assert result.file_path is None

    @pytest.mark.asyncio
    async def test_force_file_overrides_screen_mode(
        self, mock_client, path_resolver, sample_request, sample_response
    ):
        """Test that force_file creates file even for single page."""
        handler = PaginationHandler(mock_client, path_resolver)

        result = await handler.fetch_with_auto_streaming(
            request=sample_request,
            processed_first_response=sample_response,
            first_page_next_token=None,
            force_file=True,
        )

        assert result.output_mode == OutputMode.FILE
        assert result.file_path is not None
        assert result.file_path.exists()

    @pytest.mark.asyncio
    async def test_paginated_response_streams_to_file(
        self, mock_client, path_resolver, sample_request, sample_response
    ):
        """Test that paginated responses stream to file."""
        # Mock the client to return another page then no more
        mock_api_response = MagicMock()
        mock_api_response.by_entity = {}
        mock_client.fetch_obs_page.return_value = (mock_api_response, None)

        handler = PaginationHandler(mock_client, path_resolver)

        result = await handler.fetch_with_auto_streaming(
            request=sample_request,
            processed_first_response=sample_response,
            first_page_next_token="page2_token",  # Has more pages
        )

        assert result.output_mode == OutputMode.FILE
        assert result.file_path is not None
        assert result.file_path.exists()
        assert result.pages_fetched >= 1

    @pytest.mark.asyncio
    async def test_max_pages_limit_respected(
        self, mock_client, path_resolver, sample_request, sample_response
    ):
        """Test that max_pages limit is respected."""
        # Mock the client to always return another page
        mock_api_response = MagicMock()
        mock_api_response.by_entity = {}
        mock_client.fetch_obs_page.return_value = (mock_api_response, "next_token")

        handler = PaginationHandler(mock_client, path_resolver, max_pages=3)

        result = await handler.fetch_with_auto_streaming(
            request=sample_request,
            processed_first_response=sample_response,
            first_page_next_token="page2_token",
        )

        # Should stop at max_pages
        assert result.pages_fetched <= 3

    @pytest.mark.asyncio
    async def test_progress_callback_called(
        self, mock_client, path_resolver, sample_request, sample_response
    ):
        """Test that progress callback is called."""
        mock_api_response = MagicMock()
        mock_api_response.by_entity = {}
        mock_client.fetch_obs_page.return_value = (mock_api_response, None)

        callback_calls = []

        def progress_callback(page: int, rows: int, total_bytes: int):
            callback_calls.append((page, rows, total_bytes))

        handler = PaginationHandler(mock_client, path_resolver)

        await handler.fetch_with_auto_streaming(
            request=sample_request,
            processed_first_response=sample_response,
            first_page_next_token="page2_token",
            progress_callback=progress_callback,
        )

        # Should have at least one callback
        assert len(callback_calls) >= 1

    @pytest.mark.asyncio
    async def test_lineage_metadata_included(
        self, mock_client, path_resolver, sample_request, sample_response
    ):
        """Test that lineage metadata is included in CSV."""
        handler = PaginationHandler(mock_client, path_resolver, include_lineage=True)

        result = await handler.fetch_with_auto_streaming(
            request=sample_request,
            processed_first_response=sample_response,
            first_page_next_token=None,
            force_file=True,
            server_version="1.2.0",
        )

        # Read file and check for lineage headers
        with open(result.file_path) as f:
            content = f.read()

        assert "# Data Commons MCP Server Export" in content
        assert "server_version: 1.2.0" in content
        assert "variable_dcid: Count_Person" in content

    @pytest.mark.asyncio
    async def test_file_created_in_observations_directory(
        self, mock_client, path_resolver, sample_request, sample_response, temp_storage
    ):
        """Test that files are created in the observations directory."""
        handler = PaginationHandler(mock_client, path_resolver)

        result = await handler.fetch_with_auto_streaming(
            request=sample_request,
            processed_first_response=sample_response,
            first_page_next_token=None,
            force_file=True,
        )

        assert result.file_path is not None
        # Resolve both paths to handle symlinks (e.g., /var -> /private/var on macOS)
        assert result.file_path.parent.resolve() == (temp_storage / "observations").resolve()
