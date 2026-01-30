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
"""Tests for the CSV streamer utility."""

import csv
import tempfile
from pathlib import Path

import pytest
from datacommons_mcp.data_models.observations import (
    FacetMetadata,
    Node,
    ObservationToolResponse,
    PlaceObservation,
)
from datacommons_mcp.utils.csv_streamer import (
    CSVRow,
    CSVStreamer,
    StreamStats,
    flatten_response_to_rows,
)


@pytest.fixture
def temp_csv_file():
    """Create a temporary CSV file path for tests."""
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        yield Path(f.name)
    # Cleanup
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture
def sample_response():
    """Create a sample ObservationToolResponse for testing."""
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


class TestCSVRow:
    """Tests for CSVRow dataclass."""

    def test_create_csv_row(self):
        """Test creating a CSVRow."""
        row = CSVRow(
            place_dcid="geoId/06",
            place_name="California",
            place_type="State",
            variable_dcid="Count_Person",
            variable_name="Population",
            date="2020-01-01",
            value=39538223.0,
            source_id="census",
        )

        assert row.place_dcid == "geoId/06"
        assert row.value == 39538223.0

    def test_csv_row_optional_fields(self):
        """Test CSVRow with optional fields."""
        row = CSVRow(
            place_dcid="geoId/06",
            place_name=None,
            place_type=None,
            variable_dcid="Count_Person",
            variable_name=None,
            date="2020-01-01",
            value=39538223.0,
        )

        assert row.source_id is None
        assert row.place_name is None


class TestCSVStreamer:
    """Tests for CSVStreamer class."""

    def test_context_manager_creates_file(self, temp_csv_file):
        """Test that context manager creates file."""
        with CSVStreamer(temp_csv_file) as streamer:
            pass

        assert temp_csv_file.exists()

    def test_write_single_row(self, temp_csv_file):
        """Test writing a single row."""
        row = CSVRow(
            place_dcid="geoId/06",
            place_name="California",
            place_type="State",
            variable_dcid="Count_Person",
            variable_name="Population",
            date="2020-01-01",
            value=39538223.0,
            source_id="census",
        )

        with CSVStreamer(temp_csv_file, include_lineage=False) as streamer:
            streamer.write_row(row)

        # Read and verify
        with open(temp_csv_file) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1
        assert rows[0]["place_dcid"] == "geoId/06"
        assert rows[0]["value"] == "39538223.0"

    def test_write_multiple_rows(self, temp_csv_file):
        """Test writing multiple rows."""
        rows = [
            CSVRow(
                place_dcid="geoId/06",
                place_name="California",
                place_type="State",
                variable_dcid="Count_Person",
                variable_name="Population",
                date="2020-01-01",
                value=39538223.0,
            ),
            CSVRow(
                place_dcid="geoId/48",
                place_name="Texas",
                place_type="State",
                variable_dcid="Count_Person",
                variable_name="Population",
                date="2020-01-01",
                value=29145505.0,
            ),
        ]

        with CSVStreamer(temp_csv_file, include_lineage=False) as streamer:
            streamer.write_rows(iter(rows))

        with open(temp_csv_file) as f:
            reader = csv.DictReader(f)
            result_rows = list(reader)

        assert len(result_rows) == 2

    def test_stats_tracking(self, temp_csv_file):
        """Test that statistics are tracked correctly."""
        with CSVStreamer(temp_csv_file, include_lineage=False) as streamer:
            for i in range(5):
                streamer.write_row(
                    CSVRow(
                        place_dcid=f"geoId/{i:02d}",
                        place_name=f"Place {i}",
                        place_type="State",
                        variable_dcid="Count_Person",
                        variable_name="Population",
                        date="2020-01-01",
                        value=float(i * 1000),
                    )
                )

            stats = streamer.stats

        assert stats.rows_written == 5
        assert len(stats.unique_places) == 5

    def test_buffered_writes(self, temp_csv_file):
        """Test that writes are buffered correctly."""
        with CSVStreamer(
            temp_csv_file, buffer_size=3, include_lineage=False
        ) as streamer:
            # Write 5 rows (should flush after 3)
            for i in range(5):
                streamer.write_row(
                    CSVRow(
                        place_dcid=f"geoId/{i:02d}",
                        place_name=f"Place {i}",
                        place_type="State",
                        variable_dcid="Count_Person",
                        variable_name="Population",
                        date="2020-01-01",
                        value=float(i * 1000),
                    )
                )

        # All 5 should be written after context exit
        with open(temp_csv_file) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 5

    def test_write_response_page(self, temp_csv_file, sample_response):
        """Test writing a full response page."""
        with CSVStreamer(temp_csv_file, include_lineage=False) as streamer:
            rows_written = streamer.write_response_page(sample_response, page_number=1)

        assert rows_written == 4  # 2 places * 2 time points each

        with open(temp_csv_file) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 4
        # Check data integrity
        ca_rows = [r for r in rows if r["place_dcid"] == "geoId/06"]
        assert len(ca_rows) == 2

    def test_lineage_headers(self, temp_csv_file):
        """Test that lineage headers are written."""
        with CSVStreamer(temp_csv_file, include_lineage=True) as streamer:
            streamer.set_lineage_metadata(
                server_version="1.2.0",
                variable_dcid="Count_Person",
                place_dcid="country/USA",
            )
            streamer.write_row(
                CSVRow(
                    place_dcid="geoId/06",
                    place_name="California",
                    place_type="State",
                    variable_dcid="Count_Person",
                    variable_name="Population",
                    date="2020-01-01",
                    value=39538223.0,
                )
            )

        with open(temp_csv_file) as f:
            content = f.read()

        assert "# Data Commons MCP Server Export" in content
        assert "server_version: 1.2.0" in content
        assert "variable_dcid: Count_Person" in content

    def test_lineage_headers_comprehensive(self, temp_csv_file):
        """Test comprehensive lineage metadata."""
        with CSVStreamer(temp_csv_file, include_lineage=True) as streamer:
            streamer.set_lineage_metadata(
                server_version="1.2.0",
                variable_dcid="Count_Person",
                variable_name="Total Population",
                place_dcid="country/USA",
                place_name="United States of America",
                child_place_type="State",
                date_filter="range",
                date_range_start="2019-01-01",
                date_range_end="2021-12-31",
                source_id="CensusACS5YearSurvey",
                source_url="https://data.census.gov",
                timestamp="2024-01-15T10:30:00Z",
                api_version="v2",
                total_pages=5,
            )
            streamer.write_row(
                CSVRow(
                    place_dcid="geoId/06",
                    place_name="California",
                    place_type="State",
                    variable_dcid="Count_Person",
                    variable_name="Population",
                    date="2020-01-01",
                    value=39538223.0,
                )
            )

        with open(temp_csv_file) as f:
            content = f.read()

        # Check all sections are present
        assert "# Query:" in content
        assert "variable_dcid: Count_Person" in content
        assert "variable_name: Total Population" in content
        assert "place_dcid: country/USA" in content
        assert "place_name: United States of America" in content
        assert "child_place_type: State" in content

        assert "# Date Filter:" in content
        assert "date_filter: range" in content
        assert "date_range_start: 2019-01-01" in content
        assert "date_range_end: 2021-12-31" in content

        assert "# Source:" in content
        assert "source_id: CensusACS5YearSurvey" in content
        assert "source_url: https://data.census.gov" in content
        assert "api_version: v2" in content

        assert "# Export:" in content
        assert "server_version: 1.2.0" in content
        assert "timestamp: 2024-01-15T10:30:00Z" in content
        assert "total_pages: 5" in content

    def test_lineage_headers_disabled(self, temp_csv_file):
        """Test that lineage headers are not written when disabled."""
        with CSVStreamer(temp_csv_file, include_lineage=False) as streamer:
            streamer.set_lineage_metadata(
                server_version="1.2.0",
                variable_dcid="Count_Person",
            )
            streamer.write_row(
                CSVRow(
                    place_dcid="geoId/06",
                    place_name="California",
                    place_type="State",
                    variable_dcid="Count_Person",
                    variable_name="Population",
                    date="2020-01-01",
                    value=39538223.0,
                )
            )

        with open(temp_csv_file) as f:
            content = f.read()

        assert "# Data Commons MCP Server Export" not in content
        # But data should still be there
        assert "geoId/06" in content

    def test_progress_callback(self, temp_csv_file):
        """Test that progress callback is called."""
        callback_calls = []

        def callback(stats: StreamStats):
            callback_calls.append(stats.rows_written)

        with CSVStreamer(
            temp_csv_file,
            buffer_size=2,
            include_lineage=False,
            progress_callback=callback,
        ) as streamer:
            for i in range(5):
                streamer.write_row(
                    CSVRow(
                        place_dcid=f"geoId/{i:02d}",
                        place_name=f"Place {i}",
                        place_type="State",
                        variable_dcid="Count_Person",
                        variable_name="Population",
                        date="2020-01-01",
                        value=float(i * 1000),
                    )
                )

        # Callback should have been called on flushes
        assert len(callback_calls) >= 2

    def test_get_unique_places(self, temp_csv_file):
        """Test getting unique places."""
        with CSVStreamer(temp_csv_file, include_lineage=False) as streamer:
            streamer.write_row(
                CSVRow(
                    place_dcid="geoId/06",
                    place_name="California",
                    place_type="State",
                    variable_dcid="Count_Person",
                    variable_name="Population",
                    date="2020-01-01",
                    value=39538223.0,
                )
            )
            streamer.write_row(
                CSVRow(
                    place_dcid="geoId/06",  # Same place, different date
                    place_name="California",
                    place_type="State",
                    variable_dcid="Count_Person",
                    variable_name="Population",
                    date="2021-01-01",
                    value=39237836.0,
                )
            )
            streamer.write_row(
                CSVRow(
                    place_dcid="geoId/48",
                    place_name="Texas",
                    place_type="State",
                    variable_dcid="Count_Person",
                    variable_name="Population",
                    date="2020-01-01",
                    value=29145505.0,
                )
            )

            unique = streamer.get_unique_places()

        assert unique == {"geoId/06", "geoId/48"}


class TestFlattenResponseToRows:
    """Tests for the flatten_response_to_rows function."""

    def test_flatten_response(self, sample_response):
        """Test flattening a response to rows."""
        rows = list(flatten_response_to_rows(sample_response))

        assert len(rows) == 4
        assert all(isinstance(row, CSVRow) for row in rows)
        assert all(row.variable_dcid == "Count_Person" for row in rows)

    def test_flatten_empty_response(self):
        """Test flattening an empty response."""
        response = ObservationToolResponse(
            variable=Node(dcid="Count_Person"),
            place_observations=[],
            source_metadata=FacetMetadata(source_id="test"),
            alternative_sources=[],
        )

        rows = list(flatten_response_to_rows(response))
        assert len(rows) == 0

    def test_flatten_preserves_data(self, sample_response):
        """Test that flattening preserves all data correctly."""
        rows = list(flatten_response_to_rows(sample_response))

        # Find California 2020 row
        ca_2020 = [
            r for r in rows if r.place_dcid == "geoId/06" and r.date == "2020-01-01"
        ]
        assert len(ca_2020) == 1
        assert ca_2020[0].value == 39538223.0
        assert ca_2020[0].place_name == "California"
        assert ca_2020[0].place_type == "State"
