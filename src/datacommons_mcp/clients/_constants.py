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
"""Shared constants for the Data Commons clients package."""

from datacommons_mcp.version import __version__

DCID_TOPIC_PREFIX = "topic/"

# Replaces 'rc' with '.' in a version string if present.
# This is here temporarily because of validation in the DataCommonsClient
# that surface headers must only contain numbers, which will be updated
# shortly to include release candidates (TODO: lucysking)
SURFACE_HEADER_VALUE = f"mcp-{__version__.replace('rc', '.')}"

# 'x-surface' indicates to DC APIs that this call is coming from the MCP server
SURFACE_HEADER: dict[str, str] = {"x-surface": SURFACE_HEADER_VALUE}
