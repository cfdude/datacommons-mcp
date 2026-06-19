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
"""Clients for interacting with Data Commons instances.

Public surface preserved from the former single-module ``datacommons_mcp.clients``.
"""

from datacommons_mcp.clients._constants import (
    DCID_TOPIC_PREFIX,
    SURFACE_HEADER,
    SURFACE_HEADER_VALUE,
)
from datacommons_mcp.clients.base import DCClient
from datacommons_mcp.clients.factory import create_dc_client
from datacommons_mcp.clients.observations import PaginatedApiResponse

__all__ = [
    "DCID_TOPIC_PREFIX",
    "SURFACE_HEADER",
    "SURFACE_HEADER_VALUE",
    "DCClient",
    "PaginatedApiResponse",
    "create_dc_client",
]
