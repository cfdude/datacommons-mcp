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

import json
import logging
from pathlib import Path

from datacommons_client.client import DataCommonsClient

logger = logging.getLogger(__name__)

from datacommons_mcp.topics.store import (
    Node,
    TopicNodeData,
    TopicStore,
    TopicVariables,
    _flatten_variables_recursive,
)

# Constants
# Package root is one level up from this topics/ subpackage; the bundled topic
# caches live at datacommons_mcp/data/topics/.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_TYPE_TOPIC = "Topic"
_DEFAULT_TOPIC_CACHE_DIR = _PACKAGE_ROOT / "data" / "topics"
_DEFAULT_TOPIC_CACHE_PATHS = [
    _DEFAULT_TOPIC_CACHE_DIR / "topic_cache.json",
    _DEFAULT_TOPIC_CACHE_DIR / "sdg_topic_cache.json",
]


def read_topic_caches(
    file_paths: list[Path] = _DEFAULT_TOPIC_CACHE_PATHS,
) -> TopicStore:
    """
    Reads multiple topic cache files and merges them into a single TopicStore.
    """
    topic_store = TopicStore(topics_by_dcid={}, all_variables=set(), dcid_to_name={})
    for file_path in file_paths:
        logger.info("Reading topic cache from: %s", file_path)
        topic_store.merge(read_topic_cache(file_path))
    logger.info(
        "Topic store: %s topics, %s variables",
        len(topic_store.topics_by_dcid),
        len(topic_store.all_variables),
    )
    return topic_store


def read_topic_cache(file_path: Path) -> TopicStore:
    """
    Reads the topic_cache.json file, parses the hierarchical structure,
    and returns a TopicStore containing the topic map and a set of all variables.
    """
    with file_path.open("r") as f:
        # Manually process the raw JSON to handle the list-based fields
        raw_data = json.load(f)
        all_nodes: list[Node] = []
        for node_data in raw_data.get("nodes", []):
            members = node_data.get("memberList", [])
            relevant_vars = node_data.get("relevantVariableList", [])
            all_nodes.append(
                Node(
                    dcid=node_data.get("dcid", [""])[0],
                    name=node_data.get("name", [""])[0],
                    type_of=node_data.get("typeOf", [""])[0],
                    children=members + relevant_vars,
                )
            )

    # Create a lookup for all nodes by their DCID
    nodes_by_dcid: dict[str, Node] = {node.dcid: node for node in all_nodes if node.dcid}

    final_topic_variables: dict[str, TopicVariables] = {}
    all_topics = [node for node in all_nodes if node.type_of == _TYPE_TOPIC and node.dcid]

    for topic in all_topics:
        ordered_unique_vars: dict[str, None] = {}
        # NOTE: we're collecting member_variables here but not actually using them just yet.
        # See note below for when we plan to use them.
        ordered_unique_member_vars: dict[str, None] = {}
        visited_nodes: set[str] = set()

        _flatten_variables_recursive(
            topic,
            nodes_by_dcid,
            ordered_unique_member_vars,
            ordered_unique_vars,
            visited_nodes,
        )

        final_topic_variables[topic.dcid] = TopicVariables(
            topic_dcid=topic.dcid,
            topic_name=topic.name,
            # NOTE: Currently for Base DC topics, we intentionally set member_variables to the same as descendant_variables.
            # This is because we want to serve base DC topics "flattened".
            # We plan to support an explicit mode for serving topics in the future (nested vs flattened) at which time we'll flatten the topics at serve time instead of here (at load time).
            # TODO(keyurs): Set this to ordered_unique_member_vars once we support a mode for serving topics
            member_variables=list(ordered_unique_vars.keys()),
            descendant_variables=list(ordered_unique_vars.keys()),
        )

    all_variables_set: set[str] = set()
    for topic_vars in final_topic_variables.values():
        all_variables_set.update(topic_vars.descendant_variables)

    return TopicStore(topics_by_dcid=final_topic_variables, all_variables=all_variables_set)


def _fetch_node_data(
    topic_dcids: list[str], dc_client: DataCommonsClient
) -> dict[str, TopicNodeData]:
    """
    Fetch node data for the given topic DCIDs using DataCommonsClient.

    Args:
        topic_dcids: List of topic DCIDs to fetch
        dc_client: DataCommonsClient instance

    Returns:
        Dictionary mapping DCID to NodeData objects
    """
    if not topic_dcids:
        return {}

    try:
        response = dc_client.node.fetch(
            node_dcids=topic_dcids, expression="->[name, relevantVariable]"
        )

        # Create a mapping of DCID to NodeData objects
        nodes_by_dcid: dict[str, TopicNodeData] = {}

        for dcid in response.data:
            # Extract name from the arcs structure
            name_nodes = response.extract_connected_nodes(dcid, "name")
            name = name_nodes[0].value if name_nodes else ""
            # Extract relevantVariable from the arcs structure
            relevant_var_nodes = response.extract_connected_nodes(dcid, "relevantVariable")
            relevant_variables = []
            relevant_var_names = {}

            for var_node in relevant_var_nodes:
                if var_dcid := var_node.dcid:
                    relevant_variables.append(var_dcid)
                    if var_name := var_node.name:
                        relevant_var_names[var_dcid] = var_name

            nodes_by_dcid[dcid] = TopicNodeData(
                name=name,
                relevant_variables=relevant_variables,
                relevant_variable_names=relevant_var_names,
            )

        return nodes_by_dcid
    except Exception as e:
        logger.error("Error fetching node data: %s", e)
        return {}


def _save_topic_store_to_cache(topic_store: TopicStore, cache_file_path: Path) -> None:
    """
    Save a TopicStore to a cache file.

    Args:
        topic_store: The TopicStore to save
        cache_file_path: Path to the cache file
    """

    # Convert TopicStore to a serializable format
    # Note: We don't store descendant variables in the cache
    cache_data = {
        "topics_by_dcid": {
            dcid: {
                "topic_dcid": topic_data.topic_dcid,
                "topic_name": topic_data.topic_name,
                "member_variables": topic_data.member_variables,
                "member_topics": topic_data.member_topics,
            }
            for dcid, topic_data in topic_store.topics_by_dcid.items()
        },
        "all_variables": list(topic_store.all_variables),
        "dcid_to_name": topic_store.dcid_to_name,
        "root_topic_dcids": topic_store.root_topic_dcids,
    }

    # Ensure the directory exists
    cache_file_path.parent.mkdir(parents=True, exist_ok=True)

    # Save to file
    with open(cache_file_path, "w") as f:
        json.dump(cache_data, f, indent=2)


def _load_topic_store_from_cache(cache_file_path: Path) -> TopicStore:
    """
    Load a TopicStore from a cache file.

    Args:
        cache_file_path: Path to the cache file

    Returns:
        TopicStore loaded from cache
    """

    with open(cache_file_path) as f:
        cache_data = json.load(f)

    # Reconstruct TopicStore from cache data
    topics_by_dcid = {
        dcid: TopicVariables(
            topic_dcid=topic_data["topic_dcid"],
            topic_name=topic_data["topic_name"],
            member_variables=topic_data["member_variables"],
            member_topics=topic_data.get("member_topics", []),
        )
        for dcid, topic_data in cache_data["topics_by_dcid"].items()
    }

    all_variables = set(cache_data["all_variables"])
    dcid_to_name = cache_data["dcid_to_name"]
    root_topic_dcids = cache_data["root_topic_dcids"]

    topic_store = TopicStore(
        topics_by_dcid=topics_by_dcid,
        all_variables=all_variables,
        dcid_to_name=dcid_to_name,
        root_topic_dcids=root_topic_dcids,
    )

    # Populate descendant variables for each topic
    topic_store.populate_topic_descendant_variables()

    # Note: Cached data now only contains direct variables
    # Descendant variables are computed on-demand during existence checks
    logger.info("Loaded topic store from: %s", cache_file_path)

    return topic_store


def create_topic_store(
    root_topic_dcids: list[str],
    dc_client: DataCommonsClient,
    cache_file_path: Path | None = None,
) -> TopicStore:
    """
    Recursively fetch topic data using DataCommonsClient and create a TopicStore.
    If a cache file is provided and exists, load from cache. Otherwise fetch from API and cache the result.

    Args:
        root_topic_dcids: List of root topic DCIDs to fetch
        dc_client: DataCommonsClient instance
        cache_file_path: Optional path to cache file for faster loading during development

    Returns:
        TopicStore instance with topics and their variables
    """
    # Try to load from cache first
    if cache_file_path and cache_file_path.exists():
        try:
            logger.info("Loading topic store from cache: %s", cache_file_path)
            return _load_topic_store_from_cache(cache_file_path)
        except Exception as e:
            logger.warning("Failed to load from cache: %s", e)
            logger.warning("Falling back to API fetch...")

    # Fetch from API
    topics_by_dcid: dict[str, TopicVariables] = {}
    all_variables: set[str] = set()
    dcid_to_name: dict[str, str] = {}
    visited_topics: set[str] = set()
    topics_to_fetch: set[str] = set(root_topic_dcids)

    while topics_to_fetch:
        # Fetch data for current batch of topics
        current_topics = list(topics_to_fetch)
        topics_to_fetch.clear()

        nodes_data = _fetch_node_data(current_topics, dc_client)

        for topic_dcid in current_topics:
            if topic_dcid in visited_topics:
                continue

            visited_topics.add(topic_dcid)
            node_data = nodes_data.get(topic_dcid)

            if not node_data:
                continue

            # Extract topic name
            topic_name = node_data.name

            # Store topic name in dcid_to_name mapping
            if topic_name:
                dcid_to_name[topic_dcid] = topic_name

            # Extract variables and sub-topics
            member_variables = node_data.get_member_variables()
            sub_topics = node_data.get_member_topics()

            # Store variable names in dcid_to_name mapping
            variable_names = node_data.get_variable_names()
            dcid_to_name.update(variable_names)

            # Add variables to the set
            all_variables.update(member_variables)

            # Add sub-topics to the fetch queue
            for sub_topic in sub_topics:
                if sub_topic not in visited_topics:
                    topics_to_fetch.add(sub_topic)

            # Create TopicVariables for this topic
            topics_by_dcid[topic_dcid] = TopicVariables(
                topic_dcid=topic_dcid,
                topic_name=topic_name,
                member_variables=member_variables,
                member_topics=sub_topics,
            )

    topic_store = TopicStore(
        topics_by_dcid=topics_by_dcid,
        all_variables=all_variables,
        dcid_to_name=dcid_to_name,
        root_topic_dcids=root_topic_dcids,
    )

    # Populate descendant variables for each topic
    topic_store.populate_topic_descendant_variables()

    logger.info("Created topic store for: %s", dc_client.api.base_url)

    # Cache the result if a cache file path is provided
    if cache_file_path:
        try:
            logger.info("Caching topic store to: %s", cache_file_path)
            _save_topic_store_to_cache(topic_store, cache_file_path)
        except Exception as e:
            logger.error("Failed to cache topic store: %s", e)

    return topic_store
