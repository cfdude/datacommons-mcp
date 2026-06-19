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
"""Integration tests for the output handler orchestrator."""

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
from datacommons_mcp.utils.output_handler import (
    OutputHandler,
    OutputHandlerConfig,
    OutputHandlerMode,
)


@pytest.fixture
def temp_storage():
    """Create a temporary storage directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


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
            PlaceObservation(
                place=Node(dcid="geoId/48", name="Texas", type_of=["State"]),
                time_series=[
                    ("2020-01-01", 29145505.0),
                    ("2021-01-01", 29527941.0),
                ],
            ),
        ],
        source_metadata=FacetMetadata(source_id="census_pop"),
        alternative_sources=[],
    )


class TestOutputHandlerConfig:
    """Tests for OutputHandlerConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = OutputHandlerConfig()

        assert config.output_mode == OutputHandlerMode.AUTO
        assert config.output_format == "csv"
        assert config.multi_file is False
        assert config.include_lineage is True
        assert config.max_pages == 100


class TestOutputHandlerInit:
    """Tests for OutputHandler initialization."""

    def test_init_creates_components(self, mock_client, temp_storage):
        """Test that initialization creates all required components."""
        config = OutputHandlerConfig(storage_dir=temp_storage)
        handler = OutputHandler(mock_client, config)

        assert handler.client == mock_client
        assert handler.config == config
        assert handler.path_resolver is not None
        assert handler.pagination_handler is not None

    def test_init_with_default_config(self, mock_client):
        """Test initialization with default config."""
        handler = OutputHandler(mock_client)

        assert handler.config is not None
        assert handler.config.output_mode == OutputHandlerMode.AUTO


class TestOutputHandlerScreenMode:
    """Tests for screen mode output handling."""

    @pytest.mark.asyncio
    async def test_auto_mode_single_page_returns_screen(
        self, mock_client, temp_storage, sample_request, sample_response
    ):
        """Test that auto mode returns screen output for single-page responses."""
        config = OutputHandlerConfig(storage_dir=temp_storage)
        handler = OutputHandler(mock_client, config)

        result = await handler.handle_observations(
            request=sample_request,
            processed_response=sample_response,
            next_token=None,  # Single page
            output_mode=OutputHandlerMode.AUTO,
        )

        assert result.output_mode == "screen"
        assert result.data is not None
        assert result.data.variable.dcid == "Count_Person"

    @pytest.mark.asyncio
    async def test_forced_screen_mode_returns_screen(
        self, mock_client, temp_storage, sample_request, sample_response
    ):
        """Test that forced screen mode always returns screen output."""
        config = OutputHandlerConfig(storage_dir=temp_storage)
        handler = OutputHandler(mock_client, config)

        # Even with a next_token, screen mode should return directly
        result = await handler.handle_observations(
            request=sample_request,
            processed_response=sample_response,
            next_token="some_token",  # Would normally trigger file mode
            output_mode=OutputHandlerMode.SCREEN,
        )

        assert result.output_mode == "screen"
        assert result.data is not None

    @pytest.mark.asyncio
    async def test_screen_mode_string_parameter(
        self, mock_client, temp_storage, sample_request, sample_response
    ):
        """Test that string output mode parameter works."""
        config = OutputHandlerConfig(storage_dir=temp_storage)
        handler = OutputHandler(mock_client, config)

        result = await handler.handle_observations(
            request=sample_request,
            processed_response=sample_response,
            next_token=None,
            output_mode="screen",  # String instead of enum
        )

        assert result.output_mode == "screen"


class TestOutputHandlerFileMode:
    """Tests for file mode output handling."""

    @pytest.mark.asyncio
    async def test_auto_mode_paginated_creates_file(
        self, mock_client, temp_storage, sample_request, sample_response
    ):
        """Test that auto mode creates file for paginated responses."""
        # Mock the client to return no more pages after first
        mock_api_response = MagicMock()
        mock_api_response.by_entity = {}
        mock_client.fetch_obs_page.return_value = (mock_api_response, None)

        config = OutputHandlerConfig(storage_dir=temp_storage)
        handler = OutputHandler(mock_client, config)

        result = await handler.handle_observations(
            request=sample_request,
            processed_response=sample_response,
            next_token="page2_token",  # Has more pages
            output_mode=OutputHandlerMode.AUTO,
        )

        assert result.output_mode == "file"
        assert result.file_path is not None
        assert Path(result.file_path).exists()

    @pytest.mark.asyncio
    async def test_forced_file_mode_creates_file(
        self, mock_client, temp_storage, sample_request, sample_response
    ):
        """Test that forced file mode creates file even for single page."""
        config = OutputHandlerConfig(storage_dir=temp_storage)
        handler = OutputHandler(mock_client, config)

        result = await handler.handle_observations(
            request=sample_request,
            processed_response=sample_response,
            next_token=None,  # Single page
            output_mode=OutputHandlerMode.FILE,
        )

        assert result.output_mode == "file"
        assert result.file_path is not None
        assert result.rows_written is not None
        assert result.pages_fetched is not None

    @pytest.mark.asyncio
    async def test_file_mode_csv_format(
        self, mock_client, temp_storage, sample_request, sample_response
    ):
        """Test that file mode creates CSV with correct content."""
        config = OutputHandlerConfig(storage_dir=temp_storage)
        handler = OutputHandler(mock_client, config)

        result = await handler.handle_observations(
            request=sample_request,
            processed_response=sample_response,
            next_token=None,
            output_mode=OutputHandlerMode.FILE,
            output_format="csv",
        )

        assert result.output_mode == "file"
        assert result.format == "csv"

        # Verify file content
        file_path = Path(result.file_path)
        assert file_path.exists()
        content = file_path.read_text()
        assert "place_dcid" in content
        assert "date" in content
        assert "value" in content

    @pytest.mark.asyncio
    async def test_file_mode_returns_statistics(
        self, mock_client, temp_storage, sample_request, sample_response
    ):
        """Test that file mode returns correct statistics."""
        config = OutputHandlerConfig(storage_dir=temp_storage)
        handler = OutputHandler(mock_client, config)

        result = await handler.handle_observations(
            request=sample_request,
            processed_response=sample_response,
            next_token=None,
            output_mode=OutputHandlerMode.FILE,
        )

        assert result.rows_written >= 1
        assert result.pages_fetched >= 1
        assert result.file_size_bytes > 0


class TestOutputHandlerMultiFile:
    """Tests for multi-file export functionality."""

    @pytest.mark.asyncio
    async def test_multi_file_flag_passed_through(
        self, mock_client, temp_storage, sample_request, sample_response
    ):
        """Test that multi_file flag is included in result."""
        config = OutputHandlerConfig(storage_dir=temp_storage)
        handler = OutputHandler(mock_client, config)

        result = await handler.handle_observations(
            request=sample_request,
            processed_response=sample_response,
            next_token=None,
            output_mode=OutputHandlerMode.FILE,
            multi_file=True,
        )

        assert result.multi_file is True


class TestOutputHandlerEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_empty_response_screen_mode(self, mock_client, temp_storage, sample_request):
        """Test handling of empty response in screen mode."""
        empty_response = ObservationToolResponse(
            variable=Node(dcid="Count_Person", name="Population"),
            place_observations=[],
            source_metadata=FacetMetadata(source_id="census_pop"),
            alternative_sources=[],
        )

        config = OutputHandlerConfig(storage_dir=temp_storage)
        handler = OutputHandler(mock_client, config)

        result = await handler.handle_observations(
            request=sample_request,
            processed_response=empty_response,
            next_token=None,
            output_mode=OutputHandlerMode.SCREEN,
        )

        assert result.output_mode == "screen"
        assert result.data.place_observations == []

    @pytest.mark.asyncio
    async def test_empty_response_file_mode(self, mock_client, temp_storage, sample_request):
        """Test handling of empty response in file mode."""
        empty_response = ObservationToolResponse(
            variable=Node(dcid="Count_Person", name="Population"),
            place_observations=[],
            source_metadata=FacetMetadata(source_id="census_pop"),
            alternative_sources=[],
        )

        config = OutputHandlerConfig(storage_dir=temp_storage)
        handler = OutputHandler(mock_client, config)

        result = await handler.handle_observations(
            request=sample_request,
            processed_response=empty_response,
            next_token=None,
            output_mode=OutputHandlerMode.FILE,
        )

        assert result.output_mode == "file"
        # File should still be created even if empty
        assert result.file_path is not None

    @pytest.mark.asyncio
    async def test_output_format_override(
        self, mock_client, temp_storage, sample_request, sample_response
    ):
        """Test that output_format parameter overrides config."""
        config = OutputHandlerConfig(
            storage_dir=temp_storage,
            output_format="csv",  # Config says CSV
        )
        handler = OutputHandler(mock_client, config)

        result = await handler.handle_observations(
            request=sample_request,
            processed_response=sample_response,
            next_token=None,
            output_mode=OutputHandlerMode.FILE,
            output_format="json",  # Override to JSON
        )

        assert result.format == "json"


class TestScreenRowThreshold:
    """Tests for screen row threshold feature."""

    @pytest.fixture
    def large_response(self):
        """Create a response with many rows (exceeds default threshold of 500)."""
        # Create 100 places with 10 time series each = 1000 rows
        places = []
        for i in range(100):
            places.append(
                PlaceObservation(
                    place=Node(
                        dcid=f"geoId/{i:05d}",
                        name=f"Place {i}",
                        type_of=["County"],
                    ),
                    time_series=[(f"202{j}-01-01", float(i * 1000 + j)) for j in range(10)],
                )
            )

        return ObservationToolResponse(
            variable=Node(dcid="Count_Person", name="Population"),
            place_observations=places,
            source_metadata=FacetMetadata(source_id="census_pop"),
            alternative_sources=[],
        )

    @pytest.fixture
    def small_response(self):
        """Create a response with few rows (under threshold)."""
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

    def test_default_threshold(self):
        """Test default screen_row_threshold value."""
        config = OutputHandlerConfig()
        assert config.screen_row_threshold == 500

    def test_count_response_rows(self, mock_client, temp_storage, large_response):
        """Test that _count_response_rows counts correctly."""
        config = OutputHandlerConfig(storage_dir=temp_storage)
        handler = OutputHandler(mock_client, config)

        row_count = handler._count_response_rows(large_response)
        # 100 places * 10 time series each = 1000 rows
        assert row_count == 1000

    def test_count_response_rows_empty(self, mock_client, temp_storage):
        """Test row count for empty response."""
        config = OutputHandlerConfig(storage_dir=temp_storage)
        handler = OutputHandler(mock_client, config)

        empty_response = ObservationToolResponse(
            variable=Node(dcid="Count_Person", name="Population"),
            place_observations=[],
            source_metadata=FacetMetadata(source_id="census_pop"),
            alternative_sources=[],
        )

        row_count = handler._count_response_rows(empty_response)
        assert row_count == 0

    @pytest.mark.asyncio
    async def test_auto_mode_large_response_creates_file(
        self, mock_client, temp_storage, sample_request, large_response
    ):
        """Test that auto mode creates file when response exceeds threshold."""
        config = OutputHandlerConfig(
            storage_dir=temp_storage,
            screen_row_threshold=500,  # large_response has 1000 rows
        )
        handler = OutputHandler(mock_client, config)

        result = await handler.handle_observations(
            request=sample_request,
            processed_response=large_response,
            next_token=None,  # Single page, but too many rows
            output_mode=OutputHandlerMode.AUTO,
        )

        assert result.output_mode == "file"
        assert result.file_path is not None
        assert Path(result.file_path).exists()

    @pytest.mark.asyncio
    async def test_auto_mode_small_response_returns_screen(
        self, mock_client, temp_storage, sample_request, small_response
    ):
        """Test that auto mode returns screen when response is under threshold."""
        config = OutputHandlerConfig(
            storage_dir=temp_storage,
            screen_row_threshold=500,  # small_response has 2 rows
        )
        handler = OutputHandler(mock_client, config)

        result = await handler.handle_observations(
            request=sample_request,
            processed_response=small_response,
            next_token=None,  # Single page, under threshold
            output_mode=OutputHandlerMode.AUTO,
        )

        assert result.output_mode == "screen"
        assert result.data is not None

    @pytest.mark.asyncio
    async def test_threshold_boundary_at_limit_returns_screen(
        self, mock_client, temp_storage, sample_request
    ):
        """Test that response at exactly the threshold returns screen."""
        # Create response with exactly 10 rows
        response = ObservationToolResponse(
            variable=Node(dcid="Count_Person", name="Population"),
            place_observations=[
                PlaceObservation(
                    place=Node(dcid="geoId/06", name="California", type_of=["State"]),
                    time_series=[(f"20{i:02d}-01-01", float(i)) for i in range(10)],
                )
            ],
            source_metadata=FacetMetadata(source_id="census_pop"),
            alternative_sources=[],
        )

        config = OutputHandlerConfig(
            storage_dir=temp_storage,
            screen_row_threshold=10,  # Exactly at threshold
        )
        handler = OutputHandler(mock_client, config)

        result = await handler.handle_observations(
            request=sample_request,
            processed_response=response,
            next_token=None,
            output_mode=OutputHandlerMode.AUTO,
        )

        # At exactly threshold, should return screen (only > triggers file)
        assert result.output_mode == "screen"

    @pytest.mark.asyncio
    async def test_threshold_boundary_over_limit_creates_file(
        self, mock_client, temp_storage, sample_request
    ):
        """Test that response over the threshold creates file."""
        # Create response with 11 rows
        response = ObservationToolResponse(
            variable=Node(dcid="Count_Person", name="Population"),
            place_observations=[
                PlaceObservation(
                    place=Node(dcid="geoId/06", name="California", type_of=["State"]),
                    time_series=[(f"20{i:02d}-01-01", float(i)) for i in range(11)],
                )
            ],
            source_metadata=FacetMetadata(source_id="census_pop"),
            alternative_sources=[],
        )

        config = OutputHandlerConfig(
            storage_dir=temp_storage,
            screen_row_threshold=10,  # Response has 11, over threshold
        )
        handler = OutputHandler(mock_client, config)

        result = await handler.handle_observations(
            request=sample_request,
            processed_response=response,
            next_token=None,
            output_mode=OutputHandlerMode.AUTO,
        )

        assert result.output_mode == "file"

    @pytest.mark.asyncio
    async def test_forced_screen_mode_ignores_threshold(
        self, mock_client, temp_storage, sample_request, large_response
    ):
        """Test that forced screen mode ignores row threshold."""
        config = OutputHandlerConfig(
            storage_dir=temp_storage,
            screen_row_threshold=500,  # large_response has 1000 rows
        )
        handler = OutputHandler(mock_client, config)

        result = await handler.handle_observations(
            request=sample_request,
            processed_response=large_response,
            next_token=None,
            output_mode=OutputHandlerMode.SCREEN,  # Force screen
        )

        # Should return screen despite exceeding threshold
        assert result.output_mode == "screen"
        assert result.data is not None
