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

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from datacommons_mcp.data_models.observations import (
    ObservationRequest,
    ObservationToolResponse,
)
from datacommons_mcp.data_models.settings import OutputSettings, get_output_settings
from datacommons_mcp.utils.pagination_handler import (
    OutputMode,
    PaginationHandler,
)
from datacommons_mcp.utils.path_resolver import PathResolver
from datacommons_mcp.version import __version__

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

    @classmethod
    def from_settings(cls, settings: OutputSettings | None = None) -> "OutputHandlerConfig":
        """Create configuration from settings."""
        if settings is None:
            settings = get_output_settings()

        return cls(
            output_mode=OutputHandlerMode.AUTO,
            output_format=settings.output_format,
            multi_file=settings.multi_file_export,
            include_lineage=settings.include_lineage,
            max_pages=settings.max_pages,
            storage_dir=settings.storage_dir,
            screen_row_threshold=settings.screen_row_threshold,
        )


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
        self.config = config or OutputHandlerConfig.from_settings()

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
    ) -> dict[str, Any]:
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
            A standardized response dictionary with:
            - output_mode: "screen" or "file"
            - For screen mode: data (the full response)
            - For file mode: file_path, rows_written, pages_fetched, etc.
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

    def _build_screen_response(self, response: ObservationToolResponse) -> dict[str, Any]:
        """Build a standardized screen-mode response."""
        return {
            "output_mode": OutputMode.SCREEN.value,
            "data": response.model_dump(exclude_none=True),
        }

    async def _handle_file_output(
        self,
        request: ObservationRequest,
        processed_response: ObservationToolResponse,
        next_token: str | None,
        *,
        output_format: Literal["csv", "json"],
        multi_file: bool,
        progress_callback: Any | None,
    ) -> dict[str, Any]:
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

        # Build response
        response_dict = result.to_dict()

        # Add format info
        response_dict["format"] = output_format

        # Handle multi-file export (to be implemented in DC-012)
        if multi_file:
            response_dict["multi_file"] = True
            # Companion files will be added by the multi-file exporter

        return response_dict


def create_output_handler(
    client: "DCClient",
    settings: OutputSettings | None = None,
) -> OutputHandler:
    """
    Factory function to create an OutputHandler.

    Args:
        client: DCClient for API calls.
        settings: Optional OutputSettings. Uses environment if not provided.

    Returns:
        Configured OutputHandler instance.
    """
    config = OutputHandlerConfig.from_settings(settings)
    return OutputHandler(client, config)
