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
"""End-to-end tests with real Data Commons API.

These tests require a valid DC_API_KEY environment variable and make
real API calls to Data Commons. They are skipped by default and can
be run explicitly with:

    pytest tests/test_e2e.py -v --run-e2e

Or by setting the DC_API_KEY environment variable:

    DC_API_KEY=your_key pytest tests/test_e2e.py -v
"""

import os
import tempfile
from pathlib import Path

import pytest

# Skip all tests in this module if no API key is set
pytestmark = pytest.mark.skipif(
    not os.environ.get("DC_API_KEY"),
    reason="DC_API_KEY not set - skipping E2E tests",
)


@pytest.fixture
def temp_output_dir():
    """Create a temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestLiveAPIObservations:
    """End-to-end tests against live Data Commons API."""

    @pytest.mark.e2e
    async def test_single_place_returns_screen(self, temp_output_dir):
        """Single place query should return data to screen."""
        from datacommons_mcp.clients import create_dc_client
        from datacommons_mcp.config import get_dc_settings
        from datacommons_mcp.services import get_observations_paginated
        from datacommons_mcp.utils.output_handler import (
            OutputHandler,
            OutputHandlerConfig,
        )

        # Create client
        settings = get_dc_settings()
        client = create_dc_client(settings)

        # Fetch observations for a single state (should be small dataset)
        response, request, next_token = await get_observations_paginated(
            client=client,
            variable_dcid="Count_Person",
            place_dcid="geoId/06",  # California
            date="latest",
        )

        # Create output handler
        config = OutputHandlerConfig()
        config.storage_dir = temp_output_dir
        handler = OutputHandler(client, config)

        result = await handler.handle_observations(
            request=request,
            processed_response=response,
            next_token=next_token,
            output_mode="auto",
        )

        # Single place should return to screen (no pagination expected)
        assert result["output_mode"] == "screen"
        assert "data" in result
        assert result["data"]["variable"]["dcid"] == "Count_Person"
        # Should have population data for California
        place_obs = result["data"]["place_observations"]
        assert len(place_obs) > 0

    @pytest.mark.e2e
    async def test_small_child_places_may_paginate(self, temp_output_dir):
        """Child places query may paginate depending on dataset size."""
        from datacommons_mcp.clients import create_dc_client
        from datacommons_mcp.config import get_dc_settings
        from datacommons_mcp.services import get_observations_paginated
        from datacommons_mcp.utils.output_handler import (
            OutputHandler,
            OutputHandlerConfig,
        )

        # Create client
        settings = get_dc_settings()
        client = create_dc_client(settings)

        # Fetch observations for California counties
        response, request, next_token = await get_observations_paginated(
            client=client,
            variable_dcid="Count_Person",
            place_dcid="geoId/06",  # California
            child_place_type="County",
            date="2020",
        )

        # Create output handler
        config = OutputHandlerConfig()
        config.storage_dir = temp_output_dir
        handler = OutputHandler(client, config)

        result = await handler.handle_observations(
            request=request,
            processed_response=response,
            next_token=next_token,
            output_mode="auto",
        )

        # Should have data (either screen or file depending on pagination)
        if result["output_mode"] == "screen":
            assert "data" in result
            assert len(result["data"]["place_observations"]) > 0
        else:
            assert result["output_mode"] == "file"
            assert Path(result["file_path"]).exists()
            assert result["rows_written"] > 0

    @pytest.mark.e2e
    async def test_force_file_creates_csv(self, temp_output_dir):
        """Forced file mode should always create a CSV file."""
        from datacommons_mcp.clients import create_dc_client
        from datacommons_mcp.config import get_dc_settings
        from datacommons_mcp.services import get_observations_paginated
        from datacommons_mcp.utils.output_handler import (
            OutputHandler,
            OutputHandlerConfig,
        )

        # Create client
        settings = get_dc_settings()
        client = create_dc_client(settings)

        # Fetch observations for a single state
        response, request, next_token = await get_observations_paginated(
            client=client,
            variable_dcid="Count_Person",
            place_dcid="geoId/06",  # California
            date="latest",
        )

        # Create output handler with file mode
        config = OutputHandlerConfig()
        config.storage_dir = temp_output_dir
        handler = OutputHandler(client, config)

        result = await handler.handle_observations(
            request=request,
            processed_response=response,
            next_token=next_token,
            output_mode="file",  # Force file
        )

        # Should create file even for single place
        assert result["output_mode"] == "file"
        file_path = Path(result["file_path"])
        assert file_path.exists()
        assert result["rows_written"] > 0

        # Verify CSV content
        content = file_path.read_text()
        assert "Count_Person" in content
        assert "geoId/06" in content or "California" in content


class TestLiveAPILargeDataset:
    """Tests for large datasets that should trigger pagination."""

    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_us_states_population_all_years(self, temp_output_dir):
        """
        US states with all years is a larger dataset that may paginate.

        This test is marked slow and should only be run explicitly.
        """
        from datacommons_mcp.clients import create_dc_client
        from datacommons_mcp.config import get_dc_settings
        from datacommons_mcp.services import get_observations_paginated
        from datacommons_mcp.utils.output_handler import (
            OutputHandler,
            OutputHandlerConfig,
        )

        # Create client
        settings = get_dc_settings()
        client = create_dc_client(settings)

        # Fetch all years of population data for US states
        response, request, next_token = await get_observations_paginated(
            client=client,
            variable_dcid="Count_Person",
            place_dcid="country/USA",
            child_place_type="State",
            date="all",  # All years - larger dataset
        )

        # Create output handler
        config = OutputHandlerConfig()
        config.storage_dir = temp_output_dir
        handler = OutputHandler(client, config)

        result = await handler.handle_observations(
            request=request,
            processed_response=response,
            next_token=next_token,
            output_mode="auto",
        )

        # This larger dataset should have multiple data points
        if result["output_mode"] == "screen":
            # If returned to screen, verify data structure
            assert "data" in result
            place_obs = result["data"]["place_observations"]
            # Should have data for multiple states
            assert len(place_obs) >= 50  # US has 50 states + territories
        else:
            # If streamed to file, verify file
            assert result["output_mode"] == "file"
            file_path = Path(result["file_path"])
            assert file_path.exists()
            # Should have at least 50 states * some years of data
            assert result["rows_written"] >= 50


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "e2e: mark test as end-to-end (requires API key)")
    config.addinivalue_line("markers", "slow: mark test as slow (large datasets)")
