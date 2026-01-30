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
"""Tests for multi-file exporter module."""

import json
import tempfile
from pathlib import Path

import pytest
from datacommons_mcp.utils.multi_file_exporter import (
    ExportedFile,
    MultiFileExporter,
    MultiFileExportResult,
    SplitStrategy,
    create_multi_file_exporter,
)
from datacommons_mcp.utils.path_resolver import PathResolver


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def path_resolver(temp_dir):
    """Create a path resolver with temp directory."""
    return PathResolver(temp_dir)


@pytest.fixture
def exporter(path_resolver):
    """Create a multi-file exporter."""
    return create_multi_file_exporter(path_resolver, chunk_size=10)


@pytest.fixture
def sample_rows():
    """Create sample observation rows."""
    return [
        {
            "place_dcid": "geoId/06",
            "place_name": "California",
            "place_type": "State",
            "date": "2020-01",
            "value": 39538223,
        },
        {
            "place_dcid": "geoId/48",
            "place_name": "Texas",
            "place_type": "State",
            "date": "2020-01",
            "value": 29145505,
        },
        {
            "place_dcid": "geoId/06001",
            "place_name": "Alameda",
            "place_type": "County",
            "date": "2020-01",
            "value": 1671329,
        },
        {
            "place_dcid": "geoId/06002",
            "place_name": "Alpine",
            "place_type": "County",
            "date": "2020-01",
            "value": 1129,
        },
        {
            "place_dcid": "geoId/06",
            "place_name": "California",
            "place_type": "State",
            "date": "2021-01",
            "value": 39538200,
        },
        {
            "place_dcid": "geoId/48",
            "place_name": "Texas",
            "place_type": "State",
            "date": "2021-01",
            "value": 29500000,
        },
    ]


class TestSplitStrategy:
    """Tests for SplitStrategy enum."""

    def test_enum_values(self):
        """Test enum values."""
        assert SplitStrategy.NONE.value == "none"
        assert SplitStrategy.BY_PLACE.value == "by_place"
        assert SplitStrategy.BY_PLACE_TYPE.value == "by_place_type"
        assert SplitStrategy.BY_DATE.value == "by_date"
        assert SplitStrategy.BY_CHUNK.value == "by_chunk"


class TestExportedFile:
    """Tests for ExportedFile dataclass."""

    def test_create(self, temp_dir):
        """Test creating an exported file."""
        f = ExportedFile(
            file_path=temp_dir / "test.csv",
            rows=100,
            bytes=1024,
            split_key="state",
        )
        assert f.file_path == temp_dir / "test.csv"
        assert f.rows == 100
        assert f.bytes == 1024
        assert f.split_key == "state"


class TestMultiFileExportResult:
    """Tests for MultiFileExportResult dataclass."""

    def test_to_dict(self, temp_dir):
        """Test converting to dictionary."""
        result = MultiFileExportResult(
            files=[
                ExportedFile(temp_dir / "a.csv", 10, 100, "A"),
                ExportedFile(temp_dir / "b.csv", 20, 200, "B"),
            ],
            total_rows=30,
            total_bytes=300,
            manifest_path=temp_dir / "manifest.json",
            split_strategy=SplitStrategy.BY_PLACE_TYPE,
        )

        d = result.to_dict()
        assert len(d["files"]) == 2
        assert d["total_rows"] == 30
        assert d["total_bytes"] == 300
        assert d["file_count"] == 2
        assert d["split_strategy"] == "by_place_type"


class TestMultiFileExporter:
    """Tests for MultiFileExporter class."""

    def test_init(self, exporter):
        """Test exporter initialization."""
        assert exporter.chunk_size == 10

    def test_export_by_place_type(self, exporter, sample_rows):
        """Test exporting by place type."""
        result = exporter.export_by_place_type(
            rows=sample_rows,
            variable="Count_Person",
            output_format="csv",
        )

        assert result.split_strategy == SplitStrategy.BY_PLACE_TYPE
        assert len(result.files) == 2  # State and County
        assert result.total_rows == 6

        # Check that files were created
        for f in result.files:
            assert f.file_path.exists()
            assert f.split_key in ["State", "County"]

        # Check manifest
        assert result.manifest_path is not None
        assert result.manifest_path.exists()

    def test_export_by_place(self, exporter, sample_rows):
        """Test exporting by place DCID."""
        result = exporter.export_by_place(
            rows=sample_rows,
            variable="Count_Person",
            output_format="csv",
        )

        assert result.split_strategy == SplitStrategy.BY_PLACE
        assert len(result.files) == 4  # 4 unique places
        assert result.total_rows == 6

    def test_export_by_date(self, exporter, sample_rows):
        """Test exporting by date."""
        result = exporter.export_by_date(
            rows=sample_rows,
            variable="Count_Person",
            output_format="csv",
        )

        assert result.split_strategy == SplitStrategy.BY_DATE
        assert len(result.files) == 2  # 2020 and 2021
        assert result.total_rows == 6

    def test_export_by_chunk(self, exporter):
        """Test exporting by chunk."""
        rows = [{"id": i, "value": i * 10} for i in range(25)]

        result = exporter.export_by_chunk(
            rows=rows,
            variable="Test_Variable",
            chunk_size=10,
            output_format="csv",
        )

        assert result.split_strategy == SplitStrategy.BY_CHUNK
        assert len(result.files) == 3  # 25 rows / 10 = 3 chunks
        assert result.total_rows == 25

    def test_export_json_format(self, exporter, sample_rows):
        """Test exporting to JSON format."""
        result = exporter.export_by_place_type(
            rows=sample_rows,
            variable="Count_Person",
            output_format="json",
        )

        # Check files have JSON extension
        for f in result.files:
            assert f.file_path.suffix == ".json"
            assert f.file_path.exists()

            # Verify JSON is valid
            with open(f.file_path) as fp:
                data = json.load(fp)
                assert isinstance(data, list)

    def test_progress_callback(self, exporter, sample_rows):
        """Test progress callback is called."""
        progress = []

        def callback(file_idx, total_files, rows):
            progress.append((file_idx, total_files, rows))

        result = exporter.export_by_place_type(
            rows=sample_rows,
            variable="Count_Person",
            progress_callback=callback,
        )

        assert len(progress) == 2  # 2 place types
        assert progress[-1][0] == 2  # Last file index
        assert progress[-1][1] == 2  # Total files

    def test_manifest_content(self, exporter, sample_rows):
        """Test manifest file content."""
        result = exporter.export_by_place_type(
            rows=sample_rows,
            variable="Count_Person",
        )

        with open(result.manifest_path) as f:
            manifest = json.load(f)

        assert manifest["variable"] == "Count_Person"
        assert manifest["split_strategy"] == "by_place_type"
        assert manifest["total_files"] == len(result.files)
        assert manifest["total_rows"] == result.total_rows
        assert "created_at" in manifest
        assert len(manifest["files"]) == len(result.files)

    def test_sanitize_key(self, exporter):
        """Test key sanitization for file names."""
        # Test special characters
        key = "geoId/06:California State"
        sanitized = exporter._sanitize_key(key)
        assert "/" not in sanitized
        assert ":" not in sanitized
        assert " " not in sanitized

        # Test length limit
        long_key = "a" * 100
        sanitized = exporter._sanitize_key(long_key)
        assert len(sanitized) <= 50


class TestCreateMultiFileExporter:
    """Tests for factory function."""

    def test_create(self, path_resolver):
        """Test creating exporter via factory."""
        exporter = create_multi_file_exporter(path_resolver, chunk_size=500)

        assert isinstance(exporter, MultiFileExporter)
        assert exporter.chunk_size == 500
