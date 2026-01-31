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
"""Integration tests for the full observation flow."""

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
from datacommons_mcp.utils.output_handler import OutputHandler, OutputHandlerConfig


class TestOutputHandlerIntegration:
    """Test the full output handler flow with mocked client."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock DCClient."""
        client = MagicMock()
        client.fetch_obs_page = AsyncMock()
        return client

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test outputs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def sample_request(self):
        """Create a sample observation request."""
        return ObservationRequest(
            variable_dcid="Count_Person",
            place_dcid="country/USA",
            child_place_type="State",
        )

    @pytest.fixture
    def sample_response(self):
        """Create a sample observation response (first page)."""
        return ObservationToolResponse(
            variable=Node(dcid="Count_Person", name="Total Population"),
            child_place_type="State",
            source_metadata=FacetMetadata(
                source_id="census",
                import_name="US Census",
            ),
            place_observations=[
                PlaceObservation(
                    place=Node(dcid="geoId/06", name="California", type_of=["State"]),
                    time_series=[("2020", 39538223)],
                ),
                PlaceObservation(
                    place=Node(dcid="geoId/48", name="Texas", type_of=["State"]),
                    time_series=[("2020", 29145505)],
                ),
            ],
        )

    def test_single_page_returns_screen_mode(
        self, mock_client, sample_request, sample_response, temp_dir
    ):
        """Single page response (no next_token) should return screen mode."""
        import asyncio

        config = OutputHandlerConfig(storage_dir=temp_dir)
        handler = OutputHandler(mock_client, config)

        result = asyncio.run(
            handler.handle_observations(
                request=sample_request,
                processed_response=sample_response,
                next_token=None,  # No pagination
                output_mode="auto",
            )
        )

        assert result["output_mode"] == "screen"
        assert "data" in result
        assert result["data"]["variable"]["dcid"] == "Count_Person"

    def test_force_screen_mode_returns_directly(
        self, mock_client, sample_request, sample_response, temp_dir
    ):
        """Forced screen mode should return data directly even with next_token."""
        import asyncio

        config = OutputHandlerConfig(storage_dir=temp_dir)
        handler = OutputHandler(mock_client, config)

        result = asyncio.run(
            handler.handle_observations(
                request=sample_request,
                processed_response=sample_response,
                next_token="token123",  # Has pagination
                output_mode="screen",  # Force screen
            )
        )

        assert result["output_mode"] == "screen"
        assert "data" in result

    def test_force_file_mode_creates_file(
        self, mock_client, sample_request, sample_response, temp_dir
    ):
        """Forced file mode should create CSV even for single page."""
        import asyncio

        # Mock no additional pages
        mock_client.fetch_obs_page.return_value = (MagicMock(), None)

        config = OutputHandlerConfig(storage_dir=temp_dir)
        handler = OutputHandler(mock_client, config)

        result = asyncio.run(
            handler.handle_observations(
                request=sample_request,
                processed_response=sample_response,
                next_token=None,
                output_mode="file",  # Force file
            )
        )

        assert result["output_mode"] == "file"
        assert "file_path" in result
        assert "rows_written" in result
        assert "pages_fetched" in result
        assert Path(result["file_path"]).exists()

    def test_auto_mode_with_pagination_streams_to_file(
        self, mock_client, sample_request, sample_response, temp_dir
    ):
        """Auto mode with next_token should stream to file."""
        import asyncio

        # Mock second page response with no next_token (end of pagination)
        mock_response = MagicMock()
        mock_response.byVariable = {}
        mock_client.fetch_obs_page.return_value = (mock_response, None)

        config = OutputHandlerConfig(storage_dir=temp_dir)
        handler = OutputHandler(mock_client, config)

        result = asyncio.run(
            handler.handle_observations(
                request=sample_request,
                processed_response=sample_response,
                next_token="token123",  # Has more pages
                output_mode="auto",
            )
        )

        assert result["output_mode"] == "file"
        assert "file_path" in result
        assert Path(result["file_path"]).exists()
        # Should have fetched the second page
        mock_client.fetch_obs_page.assert_called()

    def test_csv_includes_lineage_headers(
        self, mock_client, sample_request, sample_response, temp_dir
    ):
        """CSV file should include lineage headers when enabled."""
        import asyncio

        config = OutputHandlerConfig(storage_dir=temp_dir, include_lineage=True)
        handler = OutputHandler(mock_client, config)

        result = asyncio.run(
            handler.handle_observations(
                request=sample_request,
                processed_response=sample_response,
                next_token=None,
                output_mode="file",
            )
        )

        file_path = Path(result["file_path"])
        content = file_path.read_text()

        # Check for lineage header markers
        assert "# ====" in content or "# Data Commons" in content
        assert "variable_dcid" in content
        assert "Count_Person" in content


class TestPaginationFlow:
    """Test pagination handling in the full flow."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock DCClient."""
        client = MagicMock()
        client.fetch_obs_page = AsyncMock()
        return client

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_max_pages_limit_respected(self, mock_client, temp_dir):
        """Should stop fetching after max_pages limit."""
        import asyncio

        # Create request and response
        request = ObservationRequest(
            variable_dcid="Count_Person",
            place_dcid="country/USA",
        )
        response = ObservationToolResponse(
            variable=Node(dcid="Count_Person"),
            source_metadata=FacetMetadata(source_id="test"),
            place_observations=[],
        )

        # Mock to always return a next_token (infinite pagination)
        mock_response = MagicMock()
        mock_response.byVariable = {}
        mock_client.fetch_obs_page.return_value = (mock_response, "next_token")

        # Set max_pages to 3
        config = OutputHandlerConfig(storage_dir=temp_dir, max_pages=3)
        handler = OutputHandler(mock_client, config)

        result = asyncio.run(
            handler.handle_observations(
                request=request,
                processed_response=response,
                next_token="first_token",
                output_mode="auto",
            )
        )

        # Should have fetched max_pages - 1 additional pages (first page already processed)
        assert mock_client.fetch_obs_page.call_count <= 2  # max_pages - 1
        assert result["output_mode"] == "file"


class TestProgressCallbacks:
    """Test progress callback handling."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock DCClient."""
        client = MagicMock()
        client.fetch_obs_page = AsyncMock()
        return client

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_progress_callback_called(self, mock_client, temp_dir):
        """Progress callback should be called during pagination."""
        import asyncio

        request = ObservationRequest(
            variable_dcid="Count_Person",
            place_dcid="country/USA",
        )
        response = ObservationToolResponse(
            variable=Node(dcid="Count_Person"),
            source_metadata=FacetMetadata(source_id="test"),
            place_observations=[
                PlaceObservation(
                    place=Node(dcid="geoId/06"),
                    time_series=[("2020", 100)],
                ),
            ],
        )

        # Mock second page
        mock_response = MagicMock()
        mock_response.byVariable = {}
        mock_client.fetch_obs_page.return_value = (mock_response, None)

        progress_calls = []

        def track_progress(page, rows, bytes_written):
            progress_calls.append((page, rows, bytes_written))

        config = OutputHandlerConfig(storage_dir=temp_dir)
        handler = OutputHandler(mock_client, config)

        asyncio.run(
            handler.handle_observations(
                request=request,
                processed_response=response,
                next_token="token",
                output_mode="auto",
                progress_callback=track_progress,
            )
        )

        # Progress should have been called at least once
        assert len(progress_calls) >= 1
