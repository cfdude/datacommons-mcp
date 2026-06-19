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
"""
Path resolver utility for secure file path handling.

Provides secure path resolution with sanitization and path traversal prevention.
"""

import re
from datetime import datetime
from enum import Enum
from pathlib import Path


class PathSecurityError(Exception):
    """Raised when a path traversal or security violation is detected."""


class FileCategory(str, Enum):
    """Categories for organizing output files."""

    OBSERVATIONS = "observations"
    SEARCH = "search"
    METADATA = "metadata"
    EXPORTS = "exports"


# Windows reserved filenames that should be blocked
WINDOWS_RESERVED_NAMES = frozenset(
    [
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    ]
)

# Regex for sanitizing filenames - keeps alphanumerics, dots, underscores, hyphens
SANITIZE_PATTERN = re.compile(r"[^A-Za-z0-9._-]")


class PathResolver:
    """
    Secure path resolver for organizing and validating output file paths.

    Organizes files into category subdirectories and prevents path traversal attacks.

    Attributes:
        storage_root: The base directory for all file storage.
    """

    def __init__(self, storage_root: Path | str) -> None:
        """
        Initialize the path resolver.

        Args:
            storage_root: Base directory for file storage. Will be created if needed.
        """
        self.storage_root = Path(storage_root).resolve()
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create storage root and category subdirectories if they don't exist."""
        self.storage_root.mkdir(parents=True, exist_ok=True)
        for category in FileCategory:
            (self.storage_root / category.value).mkdir(exist_ok=True)

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """
        Sanitize a filename by removing special characters.

        Args:
            filename: The original filename to sanitize.

        Returns:
            A sanitized filename safe for filesystem use.

        Raises:
            PathSecurityError: If the filename is reserved or would be empty.
        """
        if not filename:
            raise PathSecurityError("Empty filename not allowed")

        # Remove extension for checking
        name_part = Path(filename).stem
        ext_part = Path(filename).suffix

        # Replace unsafe characters with underscores
        sanitized = SANITIZE_PATTERN.sub("_", name_part)

        # Remove leading/trailing underscores and dots
        sanitized = sanitized.strip("_.")

        # Check for Windows reserved names
        if sanitized.upper() in WINDOWS_RESERVED_NAMES:
            sanitized = f"file_{sanitized}"

        # Ensure we have something left
        if not sanitized:
            raise PathSecurityError(f"Filename '{filename}' contains no valid characters")

        # Limit length (255 is typical max, leave room for extension)
        max_name_len = 200
        if len(sanitized) > max_name_len:
            sanitized = sanitized[:max_name_len]

        # Add back extension if present
        if ext_part:
            sanitized_ext = SANITIZE_PATTERN.sub("_", ext_part)
            return f"{sanitized}{sanitized_ext}"

        return sanitized

    def resolve(
        self,
        filename: str,
        category: FileCategory,
        *,
        create_parent: bool = True,
    ) -> Path:
        """
        Resolve a filename to a full path within the storage root.

        Args:
            filename: The filename to resolve. Will be sanitized.
            category: The category subdirectory to use.
            create_parent: Whether to create parent directories if needed.

        Returns:
            The resolved absolute path.

        Raises:
            PathSecurityError: If the resolved path escapes the storage root.
        """
        sanitized = self.sanitize_filename(filename)
        target_path = (self.storage_root / category.value / sanitized).resolve()

        # Verify path is within storage root (prevents path traversal)
        if not self._is_safe_path(target_path):
            raise PathSecurityError(
                f"Path traversal detected: {filename} resolves outside storage root"
            )

        if create_parent:
            target_path.parent.mkdir(parents=True, exist_ok=True)

        return target_path

    def _is_safe_path(self, path: Path) -> bool:
        """Check if a path is safely contained within the storage root."""
        try:
            path.resolve().relative_to(self.storage_root)
            return True
        except ValueError:
            return False

    def generate_timestamped_filename(
        self,
        prefix: str,
        variable_id: str | None = None,
        extension: str = "csv",
    ) -> str:
        """
        Generate a timestamped filename for exports.

        Args:
            prefix: Prefix for the filename (e.g., "observations").
            variable_id: Optional variable identifier to include.
            extension: File extension without dot (default: "csv").

        Returns:
            A timestamped filename like "observations_Count_Person_20240115_143052.csv"
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if variable_id:
            # Sanitize the variable ID
            safe_var = SANITIZE_PATTERN.sub("_", variable_id)
            safe_var = safe_var[:50]  # Limit length
            filename = f"{prefix}_{safe_var}_{timestamp}.{extension}"
        else:
            filename = f"{prefix}_{timestamp}.{extension}"

        return self.sanitize_filename(filename)

    def get_category_path(self, category: FileCategory) -> Path:
        """Get the path to a category subdirectory."""
        return self.storage_root / category.value

    def list_files(self, category: FileCategory, pattern: str = "*") -> list[Path]:
        """
        List files in a category directory.

        Args:
            category: The category to list files from.
            pattern: Glob pattern for filtering files.

        Returns:
            List of matching file paths.
        """
        category_path = self.get_category_path(category)
        return sorted(category_path.glob(pattern))
