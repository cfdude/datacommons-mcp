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
"""Shared utilities for FastMCP tool implementations."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp.server.context import Context

    from ..clients import DCClient
    from ..config import AppConfig
    from ..utils.output_handler import OutputHandler


@dataclass
class OutputOptions:
    """Options controlling how tool results are returned."""

    output: str = "auto"  # auto, screen, file
    format: str = "csv"  # csv, json
    multi_file: bool = False


def get_client(ctx: Context) -> DCClient:
    """Get the DC client from lifespan context."""
    return ctx.lifespan_context["client"]


def get_config(ctx: Context) -> AppConfig:
    """Get the config from lifespan context."""
    return ctx.lifespan_context["config"]


def get_output_handler(ctx: Context) -> OutputHandler:
    """Get the output handler from lifespan context."""
    return ctx.lifespan_context["output_handler"]


def extract_output_options(
    output: str | None = None,
    format: str | None = None,
    multi_file: bool = False,
) -> OutputOptions:
    """Create OutputOptions from tool parameters."""
    return OutputOptions(
        output=output or "auto",
        format=format or "csv",
        multi_file=multi_file,
    )


def format_api_error(error: Any) -> dict[str, Any]:
    """Format an API error for tool response."""
    if hasattr(error, "to_dict"):
        return error.to_dict()
    return {
        "error": {
            "code": "API_ERROR",
            "message": str(error),
        }
    }


def format_timestamp() -> str:
    """Generate a timestamp string for filenames."""
    return dt.datetime.now(dt.UTC).strftime("%Y%m%d_%H%M%S")


__all__ = [
    "OutputOptions",
    "extract_output_options",
    "format_api_error",
    "format_timestamp",
    "get_client",
    "get_config",
    "get_output_handler",
]
