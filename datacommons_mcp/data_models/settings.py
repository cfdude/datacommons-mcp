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
Pydantic settings for configuring the MCP server.
"""

from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings

from .enums import SearchScope


def _default_storage_dir() -> Path:
    """Return the default storage directory (~/Documents/datacommons-data)."""
    return Path.home() / "Documents" / "datacommons-data"


class OutputSettings(BaseSettings):
    """Settings for large dataset handling and output configuration."""

    model_config = {"env_file": ".env", "extra": "ignore", "populate_by_name": True}

    storage_dir: Path = Field(
        default_factory=_default_storage_dir,
        alias="DC_STORAGE_DIR",
        description="Directory for storing exported data files",
    )
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
    default_transport: Literal["stdio", "sse"] = Field(
        default="stdio",
        alias="DC_DEFAULT_TRANSPORT",
        description="Default transport mode for MCP server",
    )
    sse_port: int = Field(
        default=8080,
        alias="DC_SSE_PORT",
        description="Port for SSE transport server",
        ge=1,
        le=65535,
    )
    multi_file_export: bool = Field(
        default=False,
        alias="DC_MULTI_FILE_EXPORT",
        description="Enable multi-file export with companion CSVs",
    )
    include_lineage: bool = Field(
        default=True,
        alias="DC_INCLUDE_LINEAGE",
        description="Include data lineage headers in CSV exports",
    )
    screen_row_threshold: int = Field(
        default=500,
        alias="DC_SCREEN_ROW_THRESHOLD",
        description="Max rows to return to screen in auto mode; larger responses go to file",
        ge=1,
        le=10000,
    )

    @field_validator("storage_dir", mode="before")
    @classmethod
    def parse_storage_dir(cls, v: Any) -> Path:
        """Parse storage directory from string or Path, expanding ~ and making absolute."""
        if v is None or (isinstance(v, str) and not v.strip()):
            # Empty or None - use default
            return _default_storage_dir()
        if isinstance(v, Path):
            return v.expanduser().resolve()
        if isinstance(v, str):
            return Path(v).expanduser().resolve()
        raise ValueError(f"Invalid storage_dir type: {type(v)}")


def get_output_settings() -> OutputSettings:
    """Get output settings from environment."""
    return OutputSettings()


_MODEL_CONFIG = {"env_file": ".env", "extra": "ignore"}


class DCSettingsSelector(BaseSettings):
    """Settings selector to determine DC type from environment."""

    model_config = _MODEL_CONFIG

    dc_type: Literal["base", "custom"] = Field(
        default="base", alias="DC_TYPE", description="Type of Data Commons"
    )


class DCSettings(BaseSettings):
    """Settings for base Data Commons instance."""

    model_config = _MODEL_CONFIG

    api_key: str = Field(alias="DC_API_KEY", description="API key for Data Commons")

    use_search_indicators_endpoint: bool = Field(
        default=True,
        alias="DC_USE_SEARCH_INDICATORS_ENDPOINT",
        description=("Toggles between search-indicators and search-vector endpoint."),
    )


class BaseDCSettings(DCSettings):
    """Settings for base Data Commons instance."""

    def __init__(self, **kwargs: dict[str, Any]) -> None:
        super().__init__(**kwargs)

    dc_type: Literal["base"] = Field(
        default="base",
        alias="DC_TYPE",
        description="Type of Data Commons (must be 'base')",
    )
    search_root: str = Field(
        default="https://datacommons.org",
        alias="DC_SEARCH_ROOT",
        description="Search base URL for base DC",
    )
    base_index: str = Field(
        default="base_uae_mem",
        alias="DC_BASE_INDEX",
        description="Search index for base DC",
    )
    topic_cache_paths: list[str] | None = Field(
        default=None,
        alias="DC_TOPIC_CACHE_PATHS",
        description="Paths to topic cache files",
    )

    base_root_topic_dcids: list[str] | None = Field(
        default=["dc/topic/Root", "dc/topic/sdg"],
        alias="DC_BASE_ROOT_TOPIC_DCIDS",
        description="List of root topic DCIDs for base DC",
    )
    api_root: str | None = Field(
        default=None,
        alias="DC_API_ROOT",
        description="API root for local api instance",
    )

    @field_validator("topic_cache_paths", "base_root_topic_dcids", mode="before")
    @classmethod
    def parse_list_like_parameter(cls, v: str) -> list[str] | None:
        return _parse_list_like_parameter(v)


class CustomDCSettings(DCSettings):
    """Settings for custom Data Commons instance."""

    model_config = _MODEL_CONFIG

    def __init__(self, **kwargs: dict[str, Any]) -> None:
        super().__init__(**kwargs)

    dc_type: Literal["custom"] = Field(
        default="custom",
        alias="DC_TYPE",
        description="Type of Data Commons (must be 'custom')",
    )
    custom_dc_url: str = Field(
        alias="CUSTOM_DC_URL", description="Base URL for custom Data Commons instance"
    )
    api_base_url: str | None = Field(
        default=None,
        alias="DC_API_BASE_URL",
        description="API base URL (computed from base_url if not provided)",
    )
    search_scope: SearchScope = Field(
        default=SearchScope.BASE_AND_CUSTOM,
        alias="DC_SEARCH_SCOPE",
        description="Search scope for queries",
    )
    base_index: str = Field(
        default="medium_ft",
        alias="DC_BASE_INDEX",
        description="Search index for base DC",
    )
    custom_index: str = Field(
        default="user_all_minilm_mem",
        alias="DC_CUSTOM_INDEX",
        description="Search index for custom DC",
    )
    root_topic_dcids: list[str] | None = Field(
        default=None,
        alias="DC_ROOT_TOPIC_DCIDS",
        description="List of root topic DCIDs",
    )
    base_root_topic_dcids: list[str] | None = Field(
        default=["dc/topic/Root", "dc/topic/sdg"],
        alias="DC_BASE_ROOT_TOPIC_DCIDS",
        description="List of root topic DCIDs for base DC",
    )
    topic_cache_paths: list[str] | None = Field(
        default=None,
        alias="DC_TOPIC_CACHE_PATHS",
        description="Paths to topic cache files (unlikely to be used but could be useful for local development)",
    )
    # TODO (@jm-rivera): Remove once new endpoint is live.
    place_like_constraints: list[str] | None = Field(
        default=None,
        alias="PLACE_LIKE_CONSTRAINTS",
        description="List of place-like constraintProperties",
    )

    @field_validator(
        "root_topic_dcids",
        "base_root_topic_dcids",
        "place_like_constraints",
        "topic_cache_paths",
        mode="before",
    )
    @classmethod
    def parse_list_like_parameter(cls, v: str) -> list[str] | None:
        return _parse_list_like_parameter(v)

    @model_validator(mode="after")
    def compute_api_base_url(self) -> "CustomDCSettings":
        """Compute api_base_url from custom_dc_url if not provided."""
        if self.api_base_url is None:
            self.api_base_url = self.custom_dc_url.rstrip("/") + "/core/api/v2/"
        return self


def _parse_list_like_parameter(v: Any) -> list[str] | None:
    """Parse a comma-separated string or a list into a list of strings."""
    if isinstance(v, list):
        return [s for s in (str(item).strip() for item in v) if s]
    if not isinstance(v, str) or not v.strip():
        return None
    # Split by comma and strip whitespace from each item, filtering out empty strings
    return [s for s in (part.strip() for part in v.split(",")) if s]


# Union type for both settings
DCSettings = BaseDCSettings | CustomDCSettings
