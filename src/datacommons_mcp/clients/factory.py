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
"""Factory functions that build DCClient instances from settings."""

import logging
from pathlib import Path

from datacommons_client.client import DataCommonsClient

from datacommons_mcp.clients._constants import SURFACE_HEADER_VALUE
from datacommons_mcp.clients.base import DCClient
from datacommons_mcp.config import BaseDCSettings, CustomDCSettings, DCSettings
from datacommons_mcp.data_models.enums import SearchScope
from datacommons_mcp.topics import TopicStore, create_topic_store, read_topic_caches

logger = logging.getLogger(__name__)


def create_dc_client(settings: DCSettings) -> DCClient:
    """
    Factory function to create a single DCClient based on settings.

    Args:
        settings: DCSettings object containing client settings

    Returns:
        DCClient instance configured according to the provided settings

    Raises:
        ValueError: If required fields are missing or settings is invalid
    """
    if isinstance(settings, BaseDCSettings):
        return _create_base_dc_client(settings)
    if isinstance(settings, CustomDCSettings):
        return _create_custom_dc_client(settings)

    raise ValueError(
        f"Invalid settings type: {type(settings)}. Must be BaseDCSettings or CustomDCSettings"
    )


def _create_base_topic_store(settings: DCSettings) -> TopicStore:
    """Create a topic store from settings."""
    if settings.topic_cache_paths:
        paths = [Path(path) for path in settings.topic_cache_paths]
        topic_store = read_topic_caches(paths)
    else:
        topic_store = read_topic_caches()

    # Set base root topic DCIDs, they are separately specified in the settings.
    topic_store.root_topic_dcids = settings.base_root_topic_dcids

    logger.info("Base DC topic store loaded")

    return topic_store


def _create_base_dc_client(settings: BaseDCSettings) -> DCClient:
    """Create a base DC client from settings."""
    # Create topic store from path if provided else use default topic cache
    topic_store = _create_base_topic_store(settings)

    # Create DataCommonsClient, conditionally adding api_root
    dc_client_args = {
        "api_key": settings.api_key,
        "surface_header_value": SURFACE_HEADER_VALUE,
    }
    if settings.api_root:
        logger.info("Using API root for base DC: %s", settings.api_root)
        logger.info("Using search root for base DC: %s", settings.search_root)
        dc_client_args["url"] = settings.api_root
    dc = DataCommonsClient(**dc_client_args)

    # Create DCClient
    return DCClient(
        dc=dc,
        search_scope=SearchScope.BASE_ONLY,
        base_index=settings.base_index,
        custom_index=None,
        sv_search_base_url=settings.search_root,
        topic_store=topic_store,
    )


def _create_custom_dc_client(settings: CustomDCSettings) -> DCClient:
    """Create a custom DC client from settings."""
    # Use search scope directly (it's already an enum)
    search_scope = settings.search_scope

    # Create DataCommonsClient
    dc = DataCommonsClient(
        url=settings.api_base_url,
        surface_header_value=SURFACE_HEADER_VALUE,
    )

    # Create topic store if root_topic_dcids provided
    topic_store: TopicStore | None = None
    if settings.root_topic_dcids:
        topic_store = create_topic_store(settings.root_topic_dcids, dc)

    if search_scope == SearchScope.BASE_AND_CUSTOM:
        base_topic_store = _create_base_topic_store(settings)
        topic_store = topic_store.merge(base_topic_store) if topic_store else base_topic_store

    if topic_store:
        logger.info("Custom DC topic store loaded")

    # Create DCClient
    return DCClient(
        dc=dc,
        search_scope=search_scope,
        base_index=settings.base_index,
        custom_index=settings.custom_index,
        sv_search_base_url=settings.custom_dc_url,  # Use custom_dc_url as sv_search_base_url
        topic_store=topic_store,
        # TODO (@jm-rivera): Remove place-like parameter new search endpoint is live.
        _place_like_constraints=settings.place_like_constraints,
    )
