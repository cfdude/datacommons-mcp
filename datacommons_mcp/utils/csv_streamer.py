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
CSV streaming utility for writing observation data directly to disk.

Provides memory-efficient streaming writes with buffering and progress callbacks.
"""

import csv
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

from datacommons_mcp.data_models.observations import (
    ObservationToolResponse,
    PlaceObservation,
)


@dataclass
class CSVRow:
    """Represents a single flattened observation row."""

    place_dcid: str
    place_name: str | None
    place_type: str | None
    variable_dcid: str
    variable_name: str | None
    date: str
    value: float
    source_id: str | None = None


@dataclass
class StreamStats:
    """Statistics about the streaming operation."""

    rows_written: int = 0
    pages_processed: int = 0
    unique_places: set[str] = field(default_factory=set)
    bytes_written: int = 0


# Type alias for progress callback
ProgressCallback = Callable[[StreamStats], None]


class CSVStreamer:
    """
    Streams observation data to CSV files without accumulating in memory.

    Uses a context manager pattern and buffers writes for efficiency.

    Attributes:
        output_path: Path to the output CSV file.
        buffer_size: Number of rows to buffer before flushing to disk.
        include_lineage: Whether to write lineage headers as comments.
    """

    # Standard CSV headers for observation data
    HEADERS = [
        "place_dcid",
        "place_name",
        "place_type",
        "variable_dcid",
        "variable_name",
        "date",
        "value",
        "source_id",
    ]

    def __init__(
        self,
        output_path: Path | str,
        *,
        buffer_size: int = 1000,
        include_lineage: bool = True,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        """
        Initialize the CSV streamer.

        Args:
            output_path: Path to write the CSV file.
            buffer_size: Number of rows to buffer before flushing (default 1000).
            include_lineage: Whether to include lineage headers (default True).
            progress_callback: Optional callback for progress updates.
        """
        self.output_path = Path(output_path)
        self.buffer_size = buffer_size
        self.include_lineage = include_lineage
        self.progress_callback = progress_callback

        self._file: TextIO | None = None
        self._writer: csv.DictWriter | None = None
        self._buffer: list[dict[str, Any]] = []
        self._headers_written = False
        self._stats = StreamStats()
        self._lineage_metadata: dict[str, str] = {}

    def __enter__(self) -> "CSVStreamer":
        """Open the file for writing."""
        self._file = open(self.output_path, "w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=self.HEADERS)
        self._stats = StreamStats()
        self._headers_written = False
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Flush remaining data and close the file."""
        if self._buffer:
            self._flush_buffer()
        if self._file:
            self._file.close()
            self._file = None
        self._writer = None

    def set_lineage_metadata(
        self,
        *,
        server_version: str | None = None,
        variable_dcid: str | None = None,
        variable_name: str | None = None,
        place_dcid: str | None = None,
        place_name: str | None = None,
        child_place_type: str | None = None,
        date_filter: str | None = None,
        date_range_start: str | None = None,
        date_range_end: str | None = None,
        source_id: str | None = None,
        source_url: str | None = None,
        timestamp: str | None = None,
        api_version: str | None = None,
        total_pages: int | None = None,
    ) -> None:
        """
        Set metadata for lineage headers.

        Call this before writing any data to include lineage information.

        Args:
            server_version: MCP server version.
            variable_dcid: Variable DCID being queried.
            variable_name: Human-readable variable name.
            place_dcid: Place DCID being queried.
            place_name: Human-readable place name.
            child_place_type: Type of child places (e.g., "County").
            date_filter: Date filter type (e.g., "latest", "all", "range").
            date_range_start: Start of date range.
            date_range_end: End of date range.
            source_id: Data Commons source ID.
            source_url: Data Commons source URL.
            timestamp: Export timestamp.
            api_version: Data Commons API version.
            total_pages: Total number of pages fetched.
        """
        if server_version:
            self._lineage_metadata["server_version"] = server_version
        if variable_dcid:
            self._lineage_metadata["variable_dcid"] = variable_dcid
        if variable_name:
            self._lineage_metadata["variable_name"] = variable_name
        if place_dcid:
            self._lineage_metadata["place_dcid"] = place_dcid
        if place_name:
            self._lineage_metadata["place_name"] = place_name
        if child_place_type:
            self._lineage_metadata["child_place_type"] = child_place_type
        if date_filter:
            self._lineage_metadata["date_filter"] = date_filter
        if date_range_start:
            self._lineage_metadata["date_range_start"] = date_range_start
        if date_range_end:
            self._lineage_metadata["date_range_end"] = date_range_end
        if source_id:
            self._lineage_metadata["source_id"] = source_id
        if source_url:
            self._lineage_metadata["source_url"] = source_url
        if timestamp:
            self._lineage_metadata["timestamp"] = timestamp
        if api_version:
            self._lineage_metadata["api_version"] = api_version
        if total_pages is not None:
            self._lineage_metadata["total_pages"] = str(total_pages)

    def _write_lineage_headers(self) -> None:
        """Write lineage metadata as CSV comments."""
        if not self._file or not self.include_lineage:
            return

        lines = [
            "# ============================================================",
            "# Data Commons MCP Server Export",
            "# ============================================================",
        ]

        # Group metadata into sections
        query_keys = [
            "variable_dcid",
            "variable_name",
            "place_dcid",
            "place_name",
            "child_place_type",
        ]
        date_keys = ["date_filter", "date_range_start", "date_range_end"]
        source_keys = ["source_id", "source_url", "api_version"]
        export_keys = ["server_version", "timestamp", "total_pages"]

        # Query section
        query_values = {
            k: v for k, v in self._lineage_metadata.items() if k in query_keys
        }
        if query_values:
            lines.append("# Query:")
            for key, value in query_values.items():
                lines.append(f"#   {key}: {value}")

        # Date section
        date_values = {
            k: v for k, v in self._lineage_metadata.items() if k in date_keys
        }
        if date_values:
            lines.append("# Date Filter:")
            for key, value in date_values.items():
                lines.append(f"#   {key}: {value}")

        # Source section
        source_values = {
            k: v for k, v in self._lineage_metadata.items() if k in source_keys
        }
        if source_values:
            lines.append("# Source:")
            for key, value in source_values.items():
                lines.append(f"#   {key}: {value}")

        # Export section
        export_values = {
            k: v for k, v in self._lineage_metadata.items() if k in export_keys
        }
        if export_values:
            lines.append("# Export:")
            for key, value in export_values.items():
                lines.append(f"#   {key}: {value}")

        # Add any other keys not in known sections
        known_keys = set(query_keys + date_keys + source_keys + export_keys)
        other_values = {
            k: v for k, v in self._lineage_metadata.items() if k not in known_keys
        }
        if other_values:
            lines.append("# Other:")
            for key, value in other_values.items():
                lines.append(f"#   {key}: {value}")

        lines.append("# ============================================================")
        lines.append("#")  # Empty comment line before headers

        for line in lines:
            self._file.write(line + "\n")

    def _write_headers(self) -> None:
        """Write CSV headers (called once on first data)."""
        if self._headers_written or not self._writer:
            return

        if self.include_lineage:
            self._write_lineage_headers()

        self._writer.writeheader()
        self._headers_written = True

    def _flush_buffer(self) -> None:
        """Flush buffered rows to disk."""
        if not self._buffer or not self._writer:
            return

        for row in self._buffer:
            self._writer.writerow(row)

        if self._file:
            self._file.flush()
            self._stats.bytes_written = self.output_path.stat().st_size

        self._buffer.clear()

        if self.progress_callback:
            self.progress_callback(self._stats)

    def _row_to_dict(self, row: CSVRow) -> dict[str, Any]:
        """Convert a CSVRow to a dictionary for the writer."""
        return {
            "place_dcid": row.place_dcid,
            "place_name": row.place_name or "",
            "place_type": row.place_type or "",
            "variable_dcid": row.variable_dcid,
            "variable_name": row.variable_name or "",
            "date": row.date,
            "value": row.value,
            "source_id": row.source_id or "",
        }

    def write_row(self, row: CSVRow) -> None:
        """
        Write a single row to the CSV.

        Rows are buffered and flushed periodically for efficiency.

        Args:
            row: The CSVRow to write.
        """
        self._write_headers()
        self._buffer.append(self._row_to_dict(row))
        self._stats.rows_written += 1
        self._stats.unique_places.add(row.place_dcid)

        if len(self._buffer) >= self.buffer_size:
            self._flush_buffer()

    def write_rows(self, rows: Iterator[CSVRow]) -> None:
        """
        Write multiple rows to the CSV.

        Args:
            rows: Iterator of CSVRow objects to write.
        """
        for row in rows:
            self.write_row(row)

    def write_response_page(
        self,
        response: ObservationToolResponse,
        *,
        page_number: int = 1,
    ) -> int:
        """
        Write a page of observation data from an API response.

        Flattens the nested response structure to CSV rows.

        Args:
            response: The ObservationToolResponse to write.
            page_number: The page number for tracking.

        Returns:
            Number of rows written from this page.
        """
        rows_written = 0
        variable_dcid = response.variable.dcid or ""
        variable_name = response.variable.name
        source_id = (
            response.source_metadata.source_id if response.source_metadata else None
        )

        for place_obs in response.place_observations:
            rows_written += self._write_place_observation(
                place_obs,
                variable_dcid=variable_dcid,
                variable_name=variable_name,
                source_id=source_id,
            )

        self._stats.pages_processed = page_number

        if self.progress_callback:
            self.progress_callback(self._stats)

        return rows_written

    def _write_place_observation(
        self,
        place_obs: PlaceObservation,
        *,
        variable_dcid: str,
        variable_name: str | None,
        source_id: str | None,
    ) -> int:
        """Write observations for a single place."""
        rows_written = 0
        place = place_obs.place
        place_dcid = place.dcid or ""
        place_name = place.name
        place_type = place.type_of[0] if place.type_of else None

        for date, value in place_obs.time_series:
            self.write_row(
                CSVRow(
                    place_dcid=place_dcid,
                    place_name=place_name,
                    place_type=place_type,
                    variable_dcid=variable_dcid,
                    variable_name=variable_name,
                    date=date,
                    value=value,
                    source_id=source_id,
                )
            )
            rows_written += 1

        return rows_written

    @property
    def stats(self) -> StreamStats:
        """Get current streaming statistics."""
        return self._stats

    def get_unique_places(self) -> set[str]:
        """Get the set of unique place DCIDs written."""
        return self._stats.unique_places.copy()


def flatten_response_to_rows(
    response: ObservationToolResponse,
) -> Iterator[CSVRow]:
    """
    Generator that flattens an ObservationToolResponse to CSVRow objects.

    This is useful for processing responses without writing to disk.

    Args:
        response: The observation response to flatten.

    Yields:
        CSVRow objects for each observation.
    """
    variable_dcid = response.variable.dcid or ""
    variable_name = response.variable.name
    source_id = response.source_metadata.source_id if response.source_metadata else None

    for place_obs in response.place_observations:
        place = place_obs.place
        place_dcid = place.dcid or ""
        place_name = place.name
        place_type = place.type_of[0] if place.type_of else None

        for date, value in place_obs.time_series:
            yield CSVRow(
                place_dcid=place_dcid,
                place_name=place_name,
                place_type=place_type,
                variable_dcid=variable_dcid,
                variable_name=variable_name,
                date=date,
                value=value,
                source_id=source_id,
            )
