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

import asyncio
import logging
from typing import NamedTuple

from datacommons_mcp.clients import DCClient
from datacommons_mcp.data_models.search import (
    NodeInfo,
    ResolvedPlace,
    SearchResponse,
    SearchResult,
    SearchTask,
    SearchTopic,
    SearchVariable,
)
from datacommons_mcp.exceptions import DataLookupError, InvalidInputError

logger = logging.getLogger(__name__)


class _SearchPlaceContext(NamedTuple):
    parent_place_dcid: str | None
    query_places: list[str] | None
    query_place_dcids_map: dict[str, str]


async def _resolve_and_partition_places(
    client: DCClient,
    places: list[str] | None,
    parent_place: str | None,
) -> _SearchPlaceContext:
    """Resolves all place names and partitions them into parent and query places."""
    places_to_resolve = places.copy() if places else []
    if parent_place:
        places_to_resolve.append(parent_place)

    if not places_to_resolve:
        return _SearchPlaceContext(
            parent_place_dcid=None, query_places=places, query_place_dcids_map={}
        )

    place_dcids_map = await _resolve_places(client, places_to_resolve)

    query_place_dcids_map = place_dcids_map.copy()
    parent_place_dcid = None

    if parent_place:
        query_place_dcids_map.pop(parent_place, None)
        parent_place_dcid = place_dcids_map.get(parent_place)

    return _SearchPlaceContext(
        parent_place_dcid=parent_place_dcid,
        query_places=places,
        query_place_dcids_map=query_place_dcids_map,
    )


async def search_indicators(
    client: DCClient,
    query: str,
    places: list[str] | None = None,
    parent_place: str | None = None,
    per_search_limit: int = 10,
    *,
    include_topics: bool = True,
    maybe_bilateral: bool = False,
) -> SearchResponse:
    """Search for topics and/or variables."""
    # Validate parameters
    _validate_search_parameters(per_search_limit, places, parent_place)

    if not query.strip():
        # Always include topics for such queries
        include_topics = True
        if not places and not parent_place:
            # Default to World if no places are specified for such queries
            places = ["World"]

    # Resolve and partition places
    place_context = await _resolve_and_partition_places(client, places, parent_place)

    # Create search tasks based on place parameters
    search_tasks = _create_search_tasks(
        query,
        place_context.query_places,
        place_context.query_place_dcids_map,
        maybe_bilateral=maybe_bilateral,
    )

    # Use search-vector or temp impl of search-indicators endpoint
    search_result = await _search_vector(
        client=client,
        search_tasks=search_tasks,
        per_search_limit=per_search_limit,
        include_topics=include_topics,
    )

    # Collect all DCIDs for lookups
    all_dcids = _collect_all_dcids(search_result, search_tasks)
    if place_context.parent_place_dcid:
        all_dcids.add(place_context.parent_place_dcid)

    # Fetch lookups
    lookups = await _fetch_and_update_lookups(client, list(all_dcids))

    place_dcids = set(place_context.query_place_dcids_map.values())
    dcid_name_mappings = {}
    dcid_place_type_mappings = {}
    for dcid, info in lookups.items():
        dcid_name_mappings[dcid] = info.name
        if dcid in place_dcids:
            dcid_place_type_mappings[dcid] = info.type_of

    resolved_parent_place = None
    if place_context.parent_place_dcid:
        parent_info = lookups.get(place_context.parent_place_dcid)
        if parent_info:
            resolved_parent_place = ResolvedPlace(
                dcid=place_context.parent_place_dcid,
                name=parent_info.name,
                type_of=parent_info.type_of,
            )

    # Create unified response
    return SearchResponse(
        status="SUCCESS",
        dcid_name_mappings=dcid_name_mappings,
        dcid_place_type_mappings=dcid_place_type_mappings,
        topics=list(search_result.topics.values()),
        variables=list(search_result.variables.values()),
        resolved_parent_place=resolved_parent_place,
    )


def _create_search_tasks(
    query: str,
    places: list[str] | None,
    place_dcids_map: dict[str, str],
    *,
    maybe_bilateral: bool,
) -> list[SearchTask]:
    """Create search tasks based on place parameters.

    Args:
        query: The search query
        places: List of place names
        maybe_bilateral: Whether to include bilateral relationship searches
        place_dcids_map: Mapping of place names to DCIDs

    Returns:
        List of SearchTask objects
    """
    search_tasks = []
    place_dcids = (
        [place_dcids_map.get(name) for name in places if place_dcids_map.get(name)]
        if places and place_dcids_map
        else []
    )

    if places and maybe_bilateral:
        # Place-specific searches first (one per place)
        for place_name in places:
            place_dcid = place_dcids_map.get(place_name)
            if place_dcid:
                # Rewrite query to include place name and include all place DCIDs
                search_tasks.append(
                    SearchTask(query=f"{query} {place_name}", place_dcids=place_dcids)
                )

        # Original query search last
        search_tasks.append(SearchTask(query=query, place_dcids=place_dcids))

    elif places:
        # Single search task with all place DCIDs (no query rewriting)
        search_tasks.append(SearchTask(query=query, place_dcids=place_dcids))

    else:
        # No places: single search task with no place constraints
        search_tasks.append(SearchTask(query=query, place_dcids=[]))

    return search_tasks


def _validate_search_parameters(
    per_search_limit: int,
    places: list[str] | None = None,
    parent_place: str | None = None,
) -> None:
    """Validate search parameters

    Args:
        per_search_limit: Maximum results per search
        places: List of places to search for
        parent_place: Parent place to filter results

    Raises:
        ValueError: If any parameter validation fails
    """
    # Validate per_search_limit parameter
    if not 1 <= per_search_limit <= 100:
        raise InvalidInputError("per_search_limit must be between 1 and 100")

    if parent_place and not places:
        raise InvalidInputError("`places` must be specified when `parent_place` is provided.")


async def _resolve_places(
    client: DCClient,
    places: list[str] | None,
) -> dict[str, str]:
    """Resolve place names to DCIDs.

    Args:
        client: DCClient instance for place resolution
        places: List of place names

    Returns:
        Dictionary mapping place names to DCIDs

    Raises:
        DataLookupError: If place resolution fails
    """

    if not places:
        return {}

    try:
        return await client.search_places(places)
    except Exception as e:
        msg = f"Error resolving place names {places}: {type(e).__name__}: {e}"
        logger.error(msg)
        raise DataLookupError(msg) from e


def _collect_all_dcids(search_result: SearchResult, search_tasks: list[SearchTask]) -> set[str]:
    """Collect all DCIDs that need to be looked up.

    Args:
        search_result: The search result containing topics and variables
        search_tasks: List of search tasks containing place DCIDs

    Returns:
        Set of all DCIDs that need lookup (topics, variables, and places)
    """
    all_dcids = set()

    # Add topic DCIDs and their members
    for topic in search_result.topics.values():
        all_dcids.add(topic.dcid)
        all_dcids.update(topic.member_topics)
        all_dcids.update(topic.member_variables)

    # Add variable DCIDs
    all_dcids.update(search_result.variables.keys())

    # Add place DCIDs
    for search_task in search_tasks:
        all_dcids.update(search_task.place_dcids)

    return all_dcids


async def _search_vector(
    client: DCClient,
    search_tasks: list[SearchTask],
    per_search_limit: int = 10,
    *,
    include_topics: bool,
) -> SearchResult:
    """Search for indicators matching a query, optionally filtered by place existence.

    Returns:
        SearchResult: Typed result with topics and variables dictionaries
    """

    # Execute parallel searches
    tasks = []
    for search_task in search_tasks:
        task = client.fetch_indicators(
            query=search_task.query,
            place_dcids=search_task.place_dcids,
            max_results=per_search_limit,
            include_topics=include_topics,
        )
        tasks.append(task)

    # Wait for all searches to complete
    results = await asyncio.gather(*tasks)

    return await _merge_search_results(results)


async def _fetch_and_update_lookups(client: DCClient, dcids: list[str]) -> dict[str, NodeInfo]:
    """Fetch entity information for all DCIDs and return as nodes dictionary."""
    if not dcids:
        return {}

    try:
        return await client.fetch_entity_infos(dcids)
    except Exception:
        # If fetching fails, return empty dict (not an error)
        return {}


async def _merge_search_results(results: list[dict]) -> SearchResult:
    """Union results from multiple search calls."""

    # Collect all topics and variables
    all_topics: dict[str, SearchTopic] = {}
    all_variables: dict[str, SearchVariable] = {}

    for result in results:
        descriptions = result.get("descriptions", {})
        alternate_descriptions = result.get("alternate_descriptions", {})
        # Union topics
        for topic in result.get("topics", []):
            topic_dcid = topic["dcid"]
            if topic_dcid not in all_topics:
                all_topics[topic_dcid] = SearchTopic(
                    dcid=topic["dcid"],
                    member_topics=topic.get("member_topics", []),
                    member_variables=topic.get("member_variables", []),
                    places_with_data=topic.get("places_with_data"),
                    description=descriptions.get(topic_dcid),
                    alternate_descriptions=alternate_descriptions.get(topic_dcid),
                )

        # Union variables
        for variable in result.get("variables", []):
            var_dcid = variable["dcid"]
            if var_dcid not in all_variables:
                all_variables[var_dcid] = SearchVariable(
                    dcid=variable["dcid"],
                    places_with_data=variable.get("places_with_data", []),
                    description=descriptions.get(var_dcid),
                    alternate_descriptions=alternate_descriptions.get(var_dcid),
                )

    return SearchResult(topics=all_topics, variables=all_variables)
