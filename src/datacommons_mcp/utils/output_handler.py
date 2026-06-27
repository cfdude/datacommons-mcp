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
Output handler orchestrator for managing observation output modes.

Provides a high-level interface for handling observation responses with
automatic mode detection based on pagination.
"""

from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass
from enum import Enum
from itertools import islice
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from datacommons_mcp.data_models.observations import (
    ObservationPreviewRow,
    ObservationRequest,
    ObservationsFileResult,
    ObservationsResult,
    ObservationsScreenResult,
    ObservationToolResponse,
)
from datacommons_mcp.utils.csv_streamer import CSVStreamer, flatten_response_to_rows
from datacommons_mcp.utils.pagination_handler import (
    PaginationHandler,
    PaginationResult,
)
from datacommons_mcp.utils.path_resolver import PathResolver
from datacommons_mcp.version import __version__

# Number of rows included as a bounded preview in file-mode results.
_PREVIEW_ROWS = 10

if TYPE_CHECKING:
    from datacommons_mcp.clients import DCClient


class OutputHandlerMode(str, Enum):
    """User-facing output mode for tool parameters."""

    AUTO = "auto"  # Automatically detect based on pagination
    SCREEN = "screen"  # Force return data directly
    FILE = "file"  # Force file output


@dataclass
class OutputHandlerConfig:
    """Configuration for the output handler."""

    output_mode: OutputHandlerMode = OutputHandlerMode.AUTO
    output_format: Literal["csv", "json"] = "csv"
    multi_file: bool = False
    include_lineage: bool = True
    max_pages: int = 100
    storage_dir: Path | None = None
    screen_row_threshold: int = 500


class OutputHandler:
    """
    High-level orchestrator for observation output handling.

    Coordinates between the API client, pagination handler, and path resolver
    to provide a unified interface for handling observation responses.

    Key features:
    - Automatic mode detection based on pagination
    - Forced screen or file output modes
    - Standardized response format
    - Configuration from settings or direct parameters

    Attributes:
        client: The DCClient for API calls.
        config: Configuration options.
        path_resolver: PathResolver for file paths.
        pagination_handler: PaginationHandler for streaming.
    """

    def __init__(
        self,
        client: "DCClient",
        config: OutputHandlerConfig | None = None,
    ) -> None:
        """
        Initialize the output handler.

        Args:
            client: DCClient for API calls.
            config: Optional configuration. Uses settings if not provided.
        """
        self.client = client
        self.config = config or OutputHandlerConfig()

        # Initialize path resolver
        # Use configured storage_dir or default to ~/Documents/datacommons-data
        storage_dir = self.config.storage_dir or (Path.home() / "Documents" / "datacommons-data")
        self.path_resolver = PathResolver(storage_dir)

        # Initialize pagination handler
        self.pagination_handler = PaginationHandler(
            client=client,
            path_resolver=self.path_resolver,
            max_pages=self.config.max_pages,
            include_lineage=self.config.include_lineage,
        )

    async def handle_observations(
        self,
        request: ObservationRequest,
        processed_response: ObservationToolResponse,
        next_token: str | None = None,
        *,
        output_mode: OutputHandlerMode | str = OutputHandlerMode.AUTO,
        output_format: Literal["csv", "json"] | None = None,
        multi_file: bool | None = None,
        progress_callback: Any | None = None,
    ) -> ObservationsResult:
        """
        Handle observation response based on output mode.

        Args:
            request: The original observation request.
            processed_response: The processed first-page response.
            next_token: The next page token from the first page (None = no more pages).
            output_mode: Output mode ("auto", "screen", or "file").
            output_format: Output format for file mode ("csv" or "json").
            multi_file: Whether to create companion files.
            progress_callback: Optional callback for progress updates.

        Returns:
            An ``ObservationsResult`` (tagged on ``output_mode``):
            - ``ObservationsScreenResult`` (screen): ``data`` holds the full response inline.
            - ``ObservationsFileResult`` (file): ``file_path``, ``rows_written``,
              ``pages_fetched``, ``file_size_bytes``, ``unique_places_count``, ``format``.
        """
        # Normalize output mode
        if isinstance(output_mode, str):
            output_mode = OutputHandlerMode(output_mode.lower())

        # Override config if parameters provided
        format_to_use = output_format or self.config.output_format
        multi_file_to_use = multi_file if multi_file is not None else self.config.multi_file

        # Determine effective output mode
        if output_mode == OutputHandlerMode.SCREEN:
            # Force screen mode - return data directly
            return self._build_screen_response(processed_response)

        if output_mode == OutputHandlerMode.FILE:
            # Force file mode - stream to file
            return await self._handle_file_output(
                request=request,
                processed_response=processed_response,
                next_token=next_token,
                output_format=format_to_use,
                multi_file=multi_file_to_use,
                progress_callback=progress_callback,
            )

        # AUTO mode
        # Use pagination detection AND row count threshold to decide
        if next_token is not None:
            # Paginated response - stream to file
            return await self._handle_file_output(
                request=request,
                processed_response=processed_response,
                next_token=next_token,
                output_format=format_to_use,
                multi_file=multi_file_to_use,
                progress_callback=progress_callback,
            )

        # Check if single-page response exceeds row threshold
        row_count = self._count_response_rows(processed_response)
        if row_count > self.config.screen_row_threshold:
            # Response too large for screen - stream to file
            return await self._handle_file_output(
                request=request,
                processed_response=processed_response,
                next_token=next_token,
                output_format=format_to_use,
                multi_file=multi_file_to_use,
                progress_callback=progress_callback,
            )

        # Single page within threshold - return directly
        return self._build_screen_response(processed_response)

    def _count_response_rows(self, response: ObservationToolResponse) -> int:
        """Count total observation rows in the response.

        Each place may have multiple time series points, so we sum across
        all places and their time series.
        """
        return sum(len(place_obs.time_series) for place_obs in response.place_observations)

    def _build_screen_response(self, response: ObservationToolResponse) -> ObservationsScreenResult:
        """Build a typed screen-mode result with inline data."""
        return ObservationsScreenResult(output_mode="screen", data=response)

    async def _handle_file_output(
        self,
        request: ObservationRequest,
        processed_response: ObservationToolResponse,
        next_token: str | None,
        *,
        output_format: Literal["csv", "json"],
        multi_file: bool,
        progress_callback: Any | None,
    ) -> ObservationsFileResult:
        """Handle file output mode."""

        # Convert progress callback to the format expected by pagination handler
        def pagination_progress(page: int, rows: int, total_bytes: int) -> None:
            if progress_callback:
                progress_callback(page, rows, total_bytes)

        # Use pagination handler for streaming
        result = await self.pagination_handler.fetch_with_auto_streaming(
            request=request,
            processed_first_response=processed_response,
            first_page_next_token=next_token,
            force_file=True,
            progress_callback=pagination_progress,
            server_version=__version__,
        )

        # Bounded preview from the already-materialized response so the agent can see
        # the content without opening the file.
        preview = [
            ObservationPreviewRow(**asdict(row))
            for row in islice(flatten_response_to_rows(processed_response), _PREVIEW_ROWS)
        ]
        return self._finalize_file_result(
            result,
            preview_rows=preview,
            variable_name=processed_response.variable.name,
            output_format=output_format,
            multi_file=multi_file,
        )

    def _finalize_file_result(
        self,
        result: PaginationResult,
        *,
        preview_rows: list[ObservationPreviewRow],
        variable_name: str | None,
        output_format: Literal["csv", "json"],
        multi_file: bool,
        places_missing: int = 0,
    ) -> ObservationsFileResult:
        """Build the typed ObservationsFileResult from a PaginationResult + preview rows.

        Shared by the single-fetch file path and the sharded path so the result shape
        (preview/summary/columns/...) cannot drift between them.
        """
        companion_files = (
            {k: str(v) for k, v in result.companion_files.items()}
            if result.companion_files
            else None
        )
        file_path = str(result.file_path) if result.file_path else None
        summary = (
            f"{result.rows_written} rows written to {file_path} ({output_format}). "
            f"Showing the first {len(preview_rows)} of {result.rows_written} row(s); "
            f"open the file for the full dataset."
        )
        if places_missing:
            summary += (
                f" NOTE: {places_missing} requested place(s) had no data from the chosen "
                "primary source — coverage may be incomplete for this variable."
            )

        return ObservationsFileResult(
            output_mode="file",
            file_path=file_path,
            rows_written=result.rows_written,
            pages_fetched=result.pages_fetched,
            file_size_bytes=result.file_size_bytes,
            unique_places_count=len(result.unique_places),
            format=output_format,
            companion_files=companion_files,
            # Present (True) only when multi-file export was requested.
            multi_file=True if multi_file else None,
            variable_name=variable_name,
            columns=list(CSVStreamer.HEADERS),
            preview=preview_rows,
            summary=summary,
            places_missing=places_missing,
        )

    async def handle_sharded_file_output(
        self,
        request: ObservationRequest,
        pages: AsyncIterator[ObservationToolResponse],
        *,
        preview_rows: list[ObservationPreviewRow],
        variable_name: str | None,
        output_format: Literal["csv", "json"],
        places_missing: int,
        progress_callback: Any | None = None,
    ) -> ObservationsFileResult:
        """Write a sharded export (N shard pages) to one CSV and build the file result.

        Reuses the same streaming + result construction as the single-fetch path.
        multi-file companion export is NOT supported for sharded exports.
        """

        def pagination_progress(page: int, rows: int, total_bytes: int) -> None:
            if progress_callback:
                progress_callback(page, rows, total_bytes)

        result = await self.pagination_handler.stream_pages_to_file(
            request,
            pages,
            progress_callback=pagination_progress,
            server_version=__version__,
        )
        return self._finalize_file_result(
            result,
            preview_rows=preview_rows,
            variable_name=variable_name,
            output_format=output_format,
            multi_file=False,
            places_missing=places_missing,
        )
