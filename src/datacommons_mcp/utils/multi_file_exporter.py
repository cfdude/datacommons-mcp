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
Multi-file export functionality for large datasets.

Provides utilities to split large observation datasets into multiple
files based on place type, date ranges, or chunk size.
"""

import csv
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from datacommons_mcp.utils.path_resolver import FileCategory, PathResolver


class SplitStrategy(str, Enum):
    """Strategy for splitting data into multiple files."""

    NONE = "none"  # Single file (no splitting)
    BY_PLACE = "by_place"  # Split by place DCID
    BY_PLACE_TYPE = "by_place_type"  # Split by place type
    BY_DATE = "by_date"  # Split by date
    BY_CHUNK = "by_chunk"  # Split by chunk size


@dataclass
class ExportedFile:
    """Information about an exported file."""

    file_path: Path
    rows: int
    bytes: int
    split_key: str | None = None  # Key used for splitting (e.g., place type)


@dataclass
class MultiFileExportResult:
    """Result of a multi-file export operation."""

    files: list[ExportedFile] = field(default_factory=list)
    total_rows: int = 0
    total_bytes: int = 0
    manifest_path: Path | None = None
    split_strategy: SplitStrategy = SplitStrategy.NONE

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "files": [
                {
                    "path": str(f.file_path),
                    "rows": f.rows,
                    "bytes": f.bytes,
                    "split_key": f.split_key,
                }
                for f in self.files
            ],
            "total_rows": self.total_rows,
            "total_bytes": self.total_bytes,
            "manifest_path": str(self.manifest_path) if self.manifest_path else None,
            "split_strategy": self.split_strategy.value,
            "file_count": len(self.files),
        }


# Type for progress callback: (file_index, total_files, rows_in_file)
MultiFileProgressCallback = Callable[[int, int, int], None]


class MultiFileExporter:
    """
    Exporter for splitting observation data into multiple files.

    Supports various strategies for splitting data:
    - By place: One file per unique place DCID
    - By place type: One file per place type
    - By date: One file per date or date range
    - By chunk: Fixed number of rows per file

    Example:
        >>> exporter = MultiFileExporter(path_resolver)
        >>> result = exporter.export_by_place_type(
        ...     data=observations,
        ...     variable="Count_Person",
        ...     output_format="csv",
        ... )
        >>> print(result.files)
    """

    def __init__(
        self,
        path_resolver: PathResolver,
        chunk_size: int = 100000,
    ) -> None:
        """
        Initialize the multi-file exporter.

        Args:
            path_resolver: PathResolver for file path generation.
            chunk_size: Default number of rows per chunk for BY_CHUNK strategy.
        """
        self.path_resolver = path_resolver
        self.chunk_size = chunk_size

    def export_by_place_type(
        self,
        rows: list[dict[str, Any]],
        variable: str,
        *,
        output_format: Literal["csv", "json"] = "csv",
        headers: list[str] | None = None,
        progress_callback: MultiFileProgressCallback | None = None,
    ) -> MultiFileExportResult:
        """
        Export data split by place type.

        Args:
            rows: List of row dictionaries.
            variable: Variable DCID for file naming.
            output_format: Output format ("csv" or "json").
            headers: CSV headers (required for CSV format).
            progress_callback: Optional progress callback.

        Returns:
            MultiFileExportResult with export details.
        """
        # Group rows by place type
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            place_type = row.get("place_type", "unknown")
            if place_type not in groups:
                groups[place_type] = []
            groups[place_type].append(row)

        return self._export_groups(
            groups=groups,
            variable=variable,
            split_strategy=SplitStrategy.BY_PLACE_TYPE,
            output_format=output_format,
            headers=headers,
            progress_callback=progress_callback,
        )

    def export_by_place(
        self,
        rows: list[dict[str, Any]],
        variable: str,
        *,
        output_format: Literal["csv", "json"] = "csv",
        headers: list[str] | None = None,
        progress_callback: MultiFileProgressCallback | None = None,
    ) -> MultiFileExportResult:
        """
        Export data split by place DCID.

        Args:
            rows: List of row dictionaries.
            variable: Variable DCID for file naming.
            output_format: Output format ("csv" or "json").
            headers: CSV headers (required for CSV format).
            progress_callback: Optional progress callback.

        Returns:
            MultiFileExportResult with export details.
        """
        # Group rows by place DCID
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            place_dcid = row.get("place_dcid", "unknown")
            if place_dcid not in groups:
                groups[place_dcid] = []
            groups[place_dcid].append(row)

        return self._export_groups(
            groups=groups,
            variable=variable,
            split_strategy=SplitStrategy.BY_PLACE,
            output_format=output_format,
            headers=headers,
            progress_callback=progress_callback,
        )

    def export_by_date(
        self,
        rows: list[dict[str, Any]],
        variable: str,
        *,
        date_field: str = "date",
        output_format: Literal["csv", "json"] = "csv",
        headers: list[str] | None = None,
        progress_callback: MultiFileProgressCallback | None = None,
    ) -> MultiFileExportResult:
        """
        Export data split by date.

        Args:
            rows: List of row dictionaries.
            variable: Variable DCID for file naming.
            date_field: Field name containing the date.
            output_format: Output format ("csv" or "json").
            headers: CSV headers (required for CSV format).
            progress_callback: Optional progress callback.

        Returns:
            MultiFileExportResult with export details.
        """
        # Group rows by date
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            date = row.get(date_field, "unknown")
            # Extract year if full date provided
            if isinstance(date, str) and len(date) >= 4:
                year = date[:4]
            else:
                year = str(date)

            if year not in groups:
                groups[year] = []
            groups[year].append(row)

        return self._export_groups(
            groups=groups,
            variable=variable,
            split_strategy=SplitStrategy.BY_DATE,
            output_format=output_format,
            headers=headers,
            progress_callback=progress_callback,
        )

    def export_by_chunk(
        self,
        rows: list[dict[str, Any]],
        variable: str,
        *,
        chunk_size: int | None = None,
        output_format: Literal["csv", "json"] = "csv",
        headers: list[str] | None = None,
        progress_callback: MultiFileProgressCallback | None = None,
    ) -> MultiFileExportResult:
        """
        Export data split into fixed-size chunks.

        Args:
            rows: List of row dictionaries.
            variable: Variable DCID for file naming.
            chunk_size: Rows per file. Uses default if not provided.
            output_format: Output format ("csv" or "json").
            headers: CSV headers (required for CSV format).
            progress_callback: Optional progress callback.

        Returns:
            MultiFileExportResult with export details.
        """
        size = chunk_size or self.chunk_size

        # Split rows into chunks
        groups: dict[str, list[dict[str, Any]]] = {}
        for i in range(0, len(rows), size):
            chunk_num = i // size + 1
            groups[f"chunk_{chunk_num:04d}"] = rows[i : i + size]

        return self._export_groups(
            groups=groups,
            variable=variable,
            split_strategy=SplitStrategy.BY_CHUNK,
            output_format=output_format,
            headers=headers,
            progress_callback=progress_callback,
        )

    def _export_groups(
        self,
        groups: dict[str, list[dict[str, Any]]],
        variable: str,
        split_strategy: SplitStrategy,
        output_format: Literal["csv", "json"],
        headers: list[str] | None,
        progress_callback: MultiFileProgressCallback | None,
    ) -> MultiFileExportResult:
        """Export grouped data to multiple files."""
        result = MultiFileExportResult(split_strategy=split_strategy)
        total_groups = len(groups)

        for idx, (key, group_rows) in enumerate(sorted(groups.items())):
            # Generate filename with split key suffix
            suffix = self._sanitize_key(key)
            extension = output_format
            filename = self.path_resolver.generate_timestamped_filename(
                prefix=f"{variable}_{suffix}",
                extension=extension,
            )
            # Resolve to full path
            file_path = self.path_resolver.resolve(
                filename=filename,
                category=FileCategory.EXPORTS,
            )

            # Write file
            if output_format == "csv":
                bytes_written = self._write_csv(file_path, group_rows, headers)
            else:
                bytes_written = self._write_json(file_path, group_rows)

            result.files.append(
                ExportedFile(
                    file_path=file_path,
                    rows=len(group_rows),
                    bytes=bytes_written,
                    split_key=key,
                )
            )
            result.total_rows += len(group_rows)
            result.total_bytes += bytes_written

            if progress_callback:
                progress_callback(idx + 1, total_groups, len(group_rows))

        # Write manifest file
        result.manifest_path = self._write_manifest(result, variable)

        return result

    def _write_csv(
        self,
        file_path: Path,
        rows: list[dict[str, Any]],
        headers: list[str] | None,
    ) -> int:
        """Write rows to a CSV file."""
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Determine headers from first row if not provided
        if not headers and rows:
            headers = list(rows[0].keys())

        with open(file_path, "w", newline="", encoding="utf-8") as f:
            if headers:
                dict_writer = csv.DictWriter(f, fieldnames=headers)
                dict_writer.writeheader()
                dict_writer.writerows(rows)
            else:
                writer = csv.writer(f)
                for row in rows:
                    writer.writerow(list(row.values()))

        return file_path.stat().st_size

    def _write_json(
        self,
        file_path: Path,
        rows: list[dict[str, Any]],
    ) -> int:
        """Write rows to a JSON file."""
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, default=str)

        return file_path.stat().st_size

    def _write_manifest(
        self,
        result: MultiFileExportResult,
        variable: str,
    ) -> Path:
        """Write a manifest file describing all exported files."""
        manifest_filename = self.path_resolver.generate_timestamped_filename(
            prefix=f"{variable}_manifest",
            extension="json",
        )
        manifest_path = self.path_resolver.resolve(
            filename=manifest_filename,
            category=FileCategory.EXPORTS,
        )

        manifest_path.parent.mkdir(parents=True, exist_ok=True)

        manifest = {
            "created_at": datetime.now().isoformat(),
            "variable": variable,
            "split_strategy": result.split_strategy.value,
            "total_files": len(result.files),
            "total_rows": result.total_rows,
            "total_bytes": result.total_bytes,
            "files": [
                {
                    "path": str(f.file_path.name),
                    "rows": f.rows,
                    "bytes": f.bytes,
                    "split_key": f.split_key,
                }
                for f in result.files
            ],
        }

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        return manifest_path

    def _sanitize_key(self, key: str) -> str:
        """Sanitize a key for use in file names."""
        # Replace characters that are problematic in file names
        sanitized = key.replace("/", "_").replace(":", "_").replace(" ", "_")
        # Limit length
        if len(sanitized) > 50:
            sanitized = sanitized[:50]
        return sanitized


def create_multi_file_exporter(
    path_resolver: PathResolver,
    chunk_size: int = 100000,
) -> MultiFileExporter:
    """
    Factory function to create a MultiFileExporter.

    Args:
        path_resolver: PathResolver for file paths.
        chunk_size: Default chunk size for BY_CHUNK strategy.

    Returns:
        Configured MultiFileExporter instance.
    """
    return MultiFileExporter(path_resolver, chunk_size)
