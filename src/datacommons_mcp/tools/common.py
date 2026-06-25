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

import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING

from fastmcp.exceptions import ToolError

from ..exceptions import (
    DataLookupError,
    InvalidDateFormatError,
    InvalidDateRangeError,
    InvalidInputError,
    NoDataFoundError,
    ResultTooLargeError,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from fastmcp.server.context import Context

    from ..clients import DCClient
    from ..config import AppConfig

logger = logging.getLogger(__name__)

_GENERIC_ERROR_MESSAGE = "An internal error occurred while processing the request."

# Domain exceptions that carry actionable, client-safe messages. Caught
# explicitly (NOT the broad ValueError/LookupError base classes) so that
# pydantic ValidationError / KeyError / IndexError stay masked, not leaked.
_CLIENT_FACING_ERRORS = (
    InvalidInputError,
    DataLookupError,
    NoDataFoundError,
    InvalidDateFormatError,
    InvalidDateRangeError,
    ResultTooLargeError,
)


def get_client(ctx: Context) -> DCClient:
    """Get the DC client from lifespan context."""
    return ctx.lifespan_context["client"]


def get_config(ctx: Context) -> AppConfig:
    """Get the config from lifespan context."""
    return ctx.lifespan_context["config"]


@contextmanager
def tool_error_boundary() -> Iterator[None]:
    """Surface domain errors to clients, mask everything else.

    - An existing ``ToolError`` is re-raised unchanged.
    - A known client-facing domain exception becomes a ``ToolError`` carrying
      its message (so the client sees the actionable detail).
    - Any other exception is logged and re-raised as a generic ``ToolError``,
      so internal details (pydantic ``ValidationError``, ``KeyError``, bugs)
      are not leaked.
    """
    try:
        yield
    except ToolError:
        raise
    except _CLIENT_FACING_ERRORS as e:
        raise ToolError(str(e)) from e
    except Exception as e:
        logger.exception("Unexpected error in tool: %s", e)
        raise ToolError(_GENERIC_ERROR_MESSAGE) from e


__all__ = ["get_client", "get_config", "tool_error_boundary"]
