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
Pagination handler for orchestrating fetch-stream loops.

Coordinates paginated API fetches and streams data directly to CSV files
for large datasets, avoiding memory accumulation.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from datacommons_mcp.data_models.observations import (
    ObservationRequest,
    ObservationToolResponse,
)
from datacommons_mcp.utils.csv_streamer import CSVStreamer, StreamStats
from datacommons_mcp.utils.path_resolver import FileCategory, PathResolver

if TYPE_CHECKING:
    from datacommons_mcp.clients import DCClient


class OutputMode(str, Enum):
    """Mode for handling observation output."""

    SCREEN = "screen"  # Return data directly (small datasets)
    FILE = "file"  # Stream to file (large/paginated datasets)


@dataclass
class PaginationResult:
    """Result of a paginated fetch operation."""

    output_mode: OutputMode = OutputMode.SCREEN
    response: ObservationToolResponse | None = None

    # File output metadata
    file_path: Path | None = None
    rows_written: int = 0
    pages_fetched: int = 0
    file_size_bytes: int = 0
    unique_places: set[str] = field(default_factory=set)

    # Companion files for multi-file export
    companion_files: dict[str, Path] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for tool response."""
        result = {
            "output_mode": self.output_mode.value,
        }

        if self.output_mode == OutputMode.SCREEN and self.response:
            result["data"] = self.response.model_dump(exclude_none=True)
        elif self.output_mode == OutputMode.FILE:
            result["file_path"] = str(self.file_path) if self.file_path else None
            result["rows_written"] = self.rows_written
            result["pages_fetched"] = self.pages_fetched
            result["file_size_bytes"] = self.file_size_bytes
            result["unique_places_count"] = len(self.unique_places)
            if self.companion_files:
                result["companion_files"] = {
                    k: str(v) for k, v in self.companion_files.items()
                }

        return result


# Type alias for progress callback
ProgressCallback = Callable[[int, int, int], None]  # (page, rows, total_bytes)


class PaginationHandler:
    """
    Orchestrates paginated API fetches and streaming to files.

    For large datasets that require pagination, this handler:
    1. Fetches the first page to detect pagination
    2. If paginated, streams all pages directly to a CSV file
    3. If not paginated, returns data directly for screen display

    Attributes:
        client: The DCClient for making API calls.
        path_resolver: PathResolver for secure file path handling.
        max_pages: Maximum number of pages to fetch (safety limit).
        include_lineage: Whether to include lineage headers in CSV.
    """

    def __init__(
        self,
        client: "DCClient",
        path_resolver: PathResolver,
        *,
        max_pages: int = 100,
        include_lineage: bool = True,
    ) -> None:
        """
        Initialize the pagination handler.

        Args:
            client: DCClient for API calls.
            path_resolver: PathResolver for file paths.
            max_pages: Maximum pages to fetch (default 100).
            include_lineage: Include lineage headers in CSV (default True).
        """
        self.client = client
        self.path_resolver = path_resolver
        self.max_pages = max_pages
        self.include_lineage = include_lineage

    async def fetch_with_auto_streaming(
        self,
        request: ObservationRequest,
        processed_first_response: ObservationToolResponse,
        first_page_next_token: str | None,
        *,
        force_file: bool = False,
        progress_callback: ProgressCallback | None = None,
        server_version: str | None = None,
    ) -> PaginationResult:
        """
        Fetch observations with automatic pagination handling.

        If the first page indicates more pages (via next_token), streams all
        pages to a CSV file. Otherwise, returns the data directly.

        Args:
            request: The observation request parameters.
            processed_first_response: Already-processed first page response.
            first_page_next_token: Next token from first page (None = no more pages).
            force_file: Force file output even for single-page responses.
            progress_callback: Optional callback for progress updates.
            server_version: Server version for lineage headers.

        Returns:
            PaginationResult with either direct data or file metadata.
        """
        # Check if we need to paginate
        is_paginated = first_page_next_token is not None

        if not is_paginated and not force_file:
            # Single page - return directly
            return PaginationResult(
                output_mode=OutputMode.SCREEN,
                response=processed_first_response,
                pages_fetched=1,
            )

        # Multi-page or forced file - stream to CSV
        return await self._stream_to_file(
            request=request,
            first_response=processed_first_response,
            first_next_token=first_page_next_token,
            progress_callback=progress_callback,
            server_version=server_version,
        )

    async def _stream_to_file(
        self,
        request: ObservationRequest,
        first_response: ObservationToolResponse,
        first_next_token: str | None,
        *,
        progress_callback: ProgressCallback | None = None,
        server_version: str | None = None,
    ) -> PaginationResult:
        """Stream paginated observations to a CSV file."""
        # Generate filename
        variable_id = request.variable_dcid
        filename = self.path_resolver.generate_timestamped_filename(
            prefix="observations",
            variable_id=variable_id,
            extension="csv",
        )

        file_path = self.path_resolver.resolve(filename, FileCategory.OBSERVATIONS)

        def on_stream_progress(stats: StreamStats) -> None:
            if progress_callback:
                progress_callback(
                    stats.pages_processed, stats.rows_written, stats.bytes_written
                )

        with CSVStreamer(
            file_path,
            include_lineage=self.include_lineage,
            progress_callback=on_stream_progress,
        ) as streamer:
            # Set lineage metadata
            streamer.set_lineage_metadata(
                server_version=server_version,
                variable_dcid=request.variable_dcid,
                place_dcid=request.place_dcid,
                child_place_type=request.child_place_type,
                date_filter=str(request.date_type) if request.date_type else None,
                timestamp=datetime.now().isoformat(),
            )

            # Write first page
            streamer.write_response_page(first_response, page_number=1)
            pages_fetched = 1

            # Fetch remaining pages
            next_token = first_next_token
            while next_token and pages_fetched < self.max_pages:
                api_response, next_token = await self.client.fetch_obs_page(
                    request, page_token=next_token
                )

                # Process the API response into a tool response
                # Note: This is a simplified version - the full processing
                # would need to go through services.py logic
                pages_fetched += 1

                # For now, we'll write the raw observations
                # In the full implementation, this would use the
                # processed response from services.py
                self._write_api_response_page(
                    streamer, api_response, first_response, pages_fetched
                )

            # Get final stats
            stats = streamer.stats

        return PaginationResult(
            output_mode=OutputMode.FILE,
            file_path=file_path,
            rows_written=stats.rows_written,
            pages_fetched=pages_fetched,
            file_size_bytes=stats.bytes_written,
            unique_places=stats.unique_places,
        )

    def _write_api_response_page(
        self,
        streamer: CSVStreamer,
        api_response: Any,
        template_response: ObservationToolResponse,
        page_number: int,
    ) -> None:
        """
        Write a raw API response page to the streamer.

        This method bridges between the raw API response format and the
        tool response format used by the CSVStreamer.

        Args:
            streamer: The CSVStreamer to write to.
            api_response: Raw API response from fetch_obs_page.
            template_response: Template with variable/source info from first page.
            page_number: The current page number.
        """
        # The api_response contains raw observation data
        # We need to convert it to the format expected by CSVStreamer

        # Use the template response's variable and source info
        variable_dcid = template_response.variable.dcid or ""
        variable_name = template_response.variable.name
        source_id = (
            template_response.source_metadata.source_id
            if template_response.source_metadata
            else None
        )

        from datacommons_mcp.utils.csv_streamer import CSVRow

        # Extract observations from API response
        # The exact structure depends on the datacommons_client library
        if hasattr(api_response, "by_entity"):
            for entity_dcid, entity_data in api_response.by_entity.items():
                # Get place name if available
                place_name = None
                place_type = None

                # Process observations for this entity
                if hasattr(entity_data, "ordered_facets"):
                    for facet in entity_data.ordered_facets:
                        if hasattr(facet, "observations"):
                            for obs in facet.observations:
                                streamer.write_row(
                                    CSVRow(
                                        place_dcid=entity_dcid,
                                        place_name=place_name,
                                        place_type=place_type,
                                        variable_dcid=variable_dcid,
                                        variable_name=variable_name,
                                        date=obs.date if hasattr(obs, "date") else "",
                                        value=obs.value
                                        if hasattr(obs, "value")
                                        else 0.0,
                                        source_id=source_id,
                                    )
                                )
