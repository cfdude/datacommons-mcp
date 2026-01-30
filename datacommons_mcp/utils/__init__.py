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
"""Utilities for large dataset handling and common operations."""

from .csv_streamer import CSVRow, CSVStreamer, StreamStats, flatten_response_to_rows
from .date_utils import filter_by_date
from .multi_file_exporter import (
    ExportedFile,
    MultiFileExporter,
    MultiFileExportResult,
    SplitStrategy,
    create_multi_file_exporter,
)
from .output_handler import (
    OutputHandler,
    OutputHandlerConfig,
    OutputHandlerMode,
    create_output_handler,
)
from .pagination_handler import OutputMode, PaginationHandler, PaginationResult
from .path_resolver import FileCategory, PathResolver, PathSecurityError

__all__ = [
    "CSVRow",
    "CSVStreamer",
    "ExportedFile",
    "FileCategory",
    "MultiFileExporter",
    "MultiFileExportResult",
    "OutputHandler",
    "OutputHandlerConfig",
    "OutputHandlerMode",
    "OutputMode",
    "PaginationHandler",
    "PaginationResult",
    "PathResolver",
    "PathSecurityError",
    "SplitStrategy",
    "StreamStats",
    "create_multi_file_exporter",
    "create_output_handler",
    "filter_by_date",
    "flatten_response_to_rows",
]
