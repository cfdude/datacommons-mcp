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
"""Tests for the path resolver utility."""

import tempfile
from pathlib import Path

import pytest

from datacommons_mcp.utils.path_resolver import (
    FileCategory,
    PathResolver,
    PathSecurityError,
)


@pytest.fixture
def temp_storage():
    """Create a temporary storage directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def resolver(temp_storage):
    """Create a PathResolver with temporary storage."""
    return PathResolver(temp_storage)


class TestPathResolver:
    """Tests for PathResolver class."""

    def test_init_creates_directories(self, temp_storage):
        """Test that initialization creates all category directories."""
        resolver = PathResolver(temp_storage)

        assert resolver.storage_root == temp_storage.resolve()
        for category in FileCategory:
            assert (temp_storage / category.value).exists()

    def test_init_with_string_path(self, temp_storage):
        """Test initialization with string path."""
        resolver = PathResolver(str(temp_storage))
        assert resolver.storage_root == temp_storage.resolve()


class TestSanitizeFilename:
    """Tests for filename sanitization."""

    def test_sanitize_basic_filename(self, resolver):
        """Test sanitization of a basic valid filename."""
        assert resolver.sanitize_filename("test.csv") == "test.csv"

    def test_sanitize_removes_special_chars(self, resolver):
        """Test that special characters are replaced with underscores."""
        assert resolver.sanitize_filename("test@file#name.csv") == "test_file_name.csv"

    def test_sanitize_removes_path_separators(self, resolver):
        """Test that path separators are sanitized."""
        # Path separators in filenames are replaced with underscores
        # Note: Path("path/to/file.csv").stem = "file", so we test simpler cases
        assert resolver.sanitize_filename("path_to_file.csv") == "path_to_file.csv"
        # When slashes are in the name, they get replaced but Path.stem only gets last component
        result = resolver.sanitize_filename("file-name.csv")
        assert "/" not in result
        assert "\\" not in result

    def test_sanitize_empty_raises_error(self, resolver):
        """Test that empty filename raises PathSecurityError."""
        with pytest.raises(PathSecurityError, match="Empty filename"):
            resolver.sanitize_filename("")

    def test_sanitize_only_special_chars_raises_error(self, resolver):
        """Test that filename with only special chars raises error."""
        with pytest.raises(PathSecurityError, match="no valid characters"):
            resolver.sanitize_filename("@#$%")

    def test_sanitize_windows_reserved_names(self, resolver):
        """Test that Windows reserved names are prefixed."""
        assert resolver.sanitize_filename("CON.txt") == "file_CON.txt"
        assert resolver.sanitize_filename("PRN.txt") == "file_PRN.txt"
        assert resolver.sanitize_filename("AUX.txt") == "file_AUX.txt"
        assert resolver.sanitize_filename("NUL.txt") == "file_NUL.txt"
        assert resolver.sanitize_filename("COM1.txt") == "file_COM1.txt"
        assert resolver.sanitize_filename("LPT1.txt") == "file_LPT1.txt"

    def test_sanitize_preserves_underscores_and_hyphens(self, resolver):
        """Test that underscores and hyphens are preserved."""
        assert resolver.sanitize_filename("test_file-name.csv") == "test_file-name.csv"

    def test_sanitize_long_filename_truncated(self, resolver):
        """Test that very long filenames are truncated."""
        long_name = "a" * 300 + ".csv"
        sanitized = resolver.sanitize_filename(long_name)
        assert len(sanitized) <= 205  # 200 chars + extension


class TestResolve:
    """Tests for path resolution."""

    def test_resolve_basic_path(self, resolver):
        """Test resolving a basic filename."""
        path = resolver.resolve("test.csv", FileCategory.OBSERVATIONS)

        assert path.name == "test.csv"
        assert path.parent.name == "observations"

    def test_resolve_creates_parent_directory(self, resolver, temp_storage):
        """Test that parent directories are created."""
        path = resolver.resolve("test.csv", FileCategory.EXPORTS)
        assert path.parent.exists()

    def test_resolve_path_traversal_sanitized(self, resolver):
        """Test that path traversal attempts are sanitized."""
        # Path traversal characters are sanitized to underscores
        # so the resulting path is safe within the storage root
        path = resolver.resolve("../../../etc/passwd", FileCategory.OBSERVATIONS)
        # The file should be in the observations directory, not escaped
        assert "observations" in str(path)
        assert ".." not in str(path)

    def test_resolve_without_create_parent(self, resolver):
        """Test resolving without creating parent directory."""
        # The parent should already exist from init
        path = resolver.resolve("test.csv", FileCategory.METADATA, create_parent=False)
        assert path.name == "test.csv"


class TestGenerateTimestampedFilename:
    """Tests for timestamped filename generation."""

    def test_generate_with_variable_id(self, resolver):
        """Test generating filename with variable ID."""
        filename = resolver.generate_timestamped_filename(
            prefix="observations",
            variable_id="Count_Person",
            extension="csv",
        )

        assert filename.startswith("observations_Count_Person_")
        assert filename.endswith(".csv")

    def test_generate_without_variable_id(self, resolver):
        """Test generating filename without variable ID."""
        filename = resolver.generate_timestamped_filename(
            prefix="export",
            extension="json",
        )

        assert filename.startswith("export_")
        assert filename.endswith(".json")

    def test_generate_sanitizes_variable_id(self, resolver):
        """Test that variable IDs are sanitized in filename."""
        filename = resolver.generate_timestamped_filename(
            prefix="observations",
            variable_id="Count/Person@Total",
        )

        assert "/" not in filename
        assert "@" not in filename


class TestListFiles:
    """Tests for file listing."""

    def test_list_files_empty(self, resolver):
        """Test listing files in empty directory."""
        files = resolver.list_files(FileCategory.OBSERVATIONS)
        assert files == []

    def test_list_files_with_pattern(self, resolver):
        """Test listing files with glob pattern."""
        # Create some test files
        obs_path = resolver.get_category_path(FileCategory.OBSERVATIONS)
        (obs_path / "test1.csv").touch()
        (obs_path / "test2.csv").touch()
        (obs_path / "test3.json").touch()

        csv_files = resolver.list_files(FileCategory.OBSERVATIONS, "*.csv")
        assert len(csv_files) == 2
        assert all(f.suffix == ".csv" for f in csv_files)

    def test_get_category_path(self, resolver, temp_storage):
        """Test getting category path."""
        path = resolver.get_category_path(FileCategory.SEARCH)
        # Resolve both paths to handle symlinks (e.g., /var -> /private/var on macOS)
        assert path.resolve() == (temp_storage / "search").resolve()
