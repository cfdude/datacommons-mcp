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
Consolidated configuration module for Data Commons MCP server.

This module provides a flattened, centralized configuration following
FastMCP 3.0.0b1 patterns with backward-compatible accessors.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings as BaseModel

from .data_models.enums import SearchScope


def _default_storage_dir() -> Path:
    """Return the default storage directory (~/Documents/datacommons-data)."""
    return Path.home() / "Documents" / "datacommons-data"


class AppConfig(BaseModel):
    """Centralized application configuration for Data Commons MCP server.

    All settings are flattened for simplicity, with backward-compatible
    property accessors for nested access patterns.
    """

    model_config = {"env_file": ".env", "extra": "ignore", "populate_by_name": True}

    # Required: API key
    dc_api_key: str = Field(
        alias="DC_API_KEY",
        description="API key for Data Commons",
    )

    # DC instance type
    dc_type: Literal["base", "custom"] = Field(
        default="base",
        alias="DC_TYPE",
        description="Type of Data Commons instance (base or custom)",
    )

    # API configuration
    dc_api_root: str | None = Field(
        default=None,
        alias="DC_API_ROOT",
        description="API root for local API instance (base DC only)",
    )
    dc_search_root: str = Field(
        default="https://datacommons.org",
        alias="DC_SEARCH_ROOT",
        description="Search base URL for base DC",
    )
    dc_base_index: str = Field(
        default="base_uae_mem",
        alias="DC_BASE_INDEX",
        description="Search index for base DC",
    )

    # Custom DC specific
    custom_dc_url: str | None = Field(
        default=None,
        alias="CUSTOM_DC_URL",
        description="Base URL for custom Data Commons instance",
    )
    dc_custom_index: str = Field(
        default="user_all_minilm_mem",
        alias="DC_CUSTOM_INDEX",
        description="Search index for custom DC",
    )
    dc_search_scope: SearchScope = Field(
        default=SearchScope.BASE_AND_CUSTOM,
        alias="DC_SEARCH_SCOPE",
        description="Search scope for custom DC queries",
    )

    # Topic configuration
    dc_topic_cache_paths: list[str] | None = Field(
        default=None,
        alias="DC_TOPIC_CACHE_PATHS",
        description="Paths to topic cache files",
    )
    dc_root_topic_dcids: list[str] | None = Field(
        default=None,
        alias="DC_ROOT_TOPIC_DCIDS",
        description="List of root topic DCIDs (custom DC)",
    )
    dc_base_root_topic_dcids: list[str] = Field(
        default=["dc/topic/Root", "dc/topic/sdg"],
        alias="DC_BASE_ROOT_TOPIC_DCIDS",
        description="List of root topic DCIDs for base DC",
    )

    # Feature toggles
    dc_use_search_indicators: bool = Field(
        default=True,
        alias="DC_USE_SEARCH_INDICATORS_ENDPOINT",
        description="Use search-indicators vs search-vector endpoint",
    )

    # Storage configuration (flattened)
    storage_directory: str = Field(
        default_factory=lambda: str(_default_storage_dir()),
        alias="DC_STORAGE_DIR",
        description="Directory for storing exported data files",
    )

    # Output configuration (flattened)
    output_format: Literal["csv", "json"] = Field(
        default="csv",
        alias="DC_OUTPUT_FORMAT",
        description="Default format for file exports",
    )
    max_pages: int = Field(
        default=100,
        alias="DC_MAX_PAGES",
        description="Maximum number of pages to fetch in paginated requests",
        ge=1,
        le=1000,
    )
    screen_row_threshold: int = Field(
        default=500,
        alias="DC_SCREEN_ROW_THRESHOLD",
        description="Max rows to return to screen; larger responses go to file",
        ge=1,
        le=10000,
    )
    include_lineage: bool = Field(
        default=True,
        alias="DC_INCLUDE_LINEAGE",
        description="Include data lineage headers in CSV exports",
    )
    multi_file_export: bool = Field(
        default=False,
        alias="DC_MULTI_FILE_EXPORT",
        description="Enable multi-file export with companion CSVs",
    )

    # Token estimation (from mcp-fred pattern)
    safe_token_limit: int = Field(
        default=50_000,
        alias="DC_SAFE_TOKEN_LIMIT",
        description="Token limit for safe inline responses",
    )
    assume_context_used: float = Field(
        default=0.75,
        alias="DC_ASSUME_CONTEXT_USED",
        description="Assumed fraction of context already used",
    )

    # Validators
    @field_validator("storage_directory", mode="before")
    @classmethod
    def parse_storage_dir(cls, v: Any) -> str:
        """Parse storage directory from string or Path."""
        if v is None or (isinstance(v, str) and not v.strip()):
            return str(_default_storage_dir())
        if isinstance(v, Path):
            return str(v.expanduser().resolve())
        if isinstance(v, str):
            return str(Path(v).expanduser().resolve())
        raise ValueError(f"Invalid storage_directory type: {type(v)}")

    @field_validator("dc_topic_cache_paths", "dc_root_topic_dcids", mode="before")
    @classmethod
    def parse_list_field(cls, v: Any) -> list[str] | None:
        """Parse comma-separated string or list into list of strings."""
        if isinstance(v, list):
            return [s for s in (str(item).strip() for item in v) if s]
        if not isinstance(v, str) or not v.strip():
            return None
        return [s for s in (part.strip() for part in v.split(",")) if s]

    # Backward-compatible property accessors
    @property
    def storage(self) -> _CompatStorage:
        """Backward-compatible storage settings accessor."""
        return _CompatStorage(directory=self.storage_directory)

    @property
    def output(self) -> _CompatOutput:
        """Backward-compatible output settings accessor."""
        return _CompatOutput(
            format=self.output_format,
            screen_row_threshold=self.screen_row_threshold,
            safe_token_limit=self.safe_token_limit,
            assume_context_used=self.assume_context_used,
            include_lineage=self.include_lineage,
            multi_file_export=self.multi_file_export,
            max_pages=self.max_pages,
        )


@dataclass
class _CompatStorage:
    """Backward-compatible storage settings."""

    directory: str

    @property
    def path(self) -> Path:
        return Path(self.directory)


@dataclass
class _CompatOutput:
    """Backward-compatible output settings."""

    format: str
    screen_row_threshold: int
    safe_token_limit: int
    assume_context_used: float
    include_lineage: bool
    multi_file_export: bool
    max_pages: int


def load_config() -> AppConfig:
    """Load configuration from environment variables.

    Returns:
        AppConfig instance with settings from environment.

    Raises:
        ValidationError: If required settings are missing or invalid.
    """
    return AppConfig()  # type: ignore[call-arg]


__all__ = ["AppConfig", "load_config"]
