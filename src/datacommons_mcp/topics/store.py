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

import logging
from dataclasses import dataclass, field
from typing import Self

logger = logging.getLogger(__name__)


# Constants
_DCID_PREFIX_TOPIC = "topic/"
_DCID_PREFIX_SVPG = "svpg/"


@dataclass
class Node:
    """Represents a generic node in the topic hierarchy."""

    dcid: str
    name: str
    type_of: str
    children: list[str] = field(default_factory=list)


@dataclass
class TopicVariables:
    """Represents a topic and its members (both sub-topics and variables)."""

    topic_dcid: str
    topic_name: str
    member_variables: list[str] = field(default_factory=list)
    descendant_variables: list[str] = field(default_factory=list)
    member_topics: list[str] = field(default_factory=list)


@dataclass
class TopicNodeData:
    """Represents the parsed topic data from a node API response."""

    name: str
    relevant_variables: list[str]
    # Maps the dcids of the `relevant_variables` to their name(s)
    relevant_variable_names: dict[str, str] = field(default_factory=dict)

    def get_member_variables(self) -> list[str]:
        """Extract variable DCIDs from relevant_variables."""
        return [var for var in self.relevant_variables if not _is_topic_dcid(var)]

    def get_member_topics(self) -> list[str]:
        """Extract topic DCIDs from relevant_variables."""
        return [var for var in self.relevant_variables if _is_topic_dcid(var)]

    def get_variable_names(self) -> dict[str, str]:
        """Get the mapping of variable DCIDs to their names."""
        return {
            dcid: name
            for dcid, name in self.relevant_variable_names.items()
            if not _is_topic_dcid(dcid)
        }

    def get_topic_names(self) -> dict[str, str]:
        """Get the mapping of topic DCIDs to their names."""
        return {
            dcid: name
            for dcid, name in self.relevant_variable_names.items()
            if _is_topic_dcid(dcid)
        }


@dataclass
class TopicStore:
    """A wrapper for the topic cache data."""

    topics_by_dcid: dict[str, TopicVariables]
    all_variables: set[str]
    dcid_to_name: dict[str, str] = field(default_factory=dict)
    root_topic_dcids: list[str] = field(default_factory=list)

    def has_variable(self, sv_dcid: str) -> bool:
        return sv_dcid in self.all_variables

    def get_topic_member_variables(self, topic_dcid: str) -> list[str]:
        topic_data = self.topics_by_dcid.get(topic_dcid)
        return topic_data.member_variables if topic_data else []

    def get_topic_descendant_variables(self, topic_dcid: str) -> list[str]:
        topic_data = self.topics_by_dcid.get(topic_dcid)
        return topic_data.descendant_variables if topic_data else []

    # Recursively fetch descendant variables using dict to maintain insertion order
    # This is used to populate TopicVariables.descendant_variables
    def _collect_topic_descendant_variables(
        self, topic_dcid: str, visited: set[str] | None = None
    ) -> dict[str, None]:
        if visited is None:
            visited = set()
        if topic_dcid in visited:
            return {}
        visited.add(topic_dcid)
        topic = self.topics_by_dcid.get(topic_dcid)
        if not topic:
            return {}
        # Use dict as ordered set for direct member variables
        descendant_vars = dict.fromkeys(topic.member_variables, None)
        # Recurse into member topics
        for sub_topic_dcid in topic.member_topics:
            descendant_vars.update(
                self._collect_topic_descendant_variables(sub_topic_dcid, visited)
            )
        return descendant_vars

    def populate_topic_descendant_variables(self) -> None:
        """Populate descendant variables for each topic."""
        for topic_dcid in self.topics_by_dcid:
            self.topics_by_dcid[topic_dcid].descendant_variables = list(
                self._collect_topic_descendant_variables(topic_dcid).keys()
            )

    def get_topic_members(self, topic_dcid: str) -> list[str]:
        """Get both member topics and variables for a topic."""
        topic_data = self.topics_by_dcid.get(topic_dcid)
        if not topic_data:
            return []
        return topic_data.member_topics + topic_data.member_variables

    def get_member_topics(self, topic_dcid: str) -> list[str]:
        """Get only member topics (not variables) for a topic."""
        topic_data = self.topics_by_dcid.get(topic_dcid)
        return topic_data.member_topics if topic_data else []

    def get_name(self, dcid: str) -> str:
        """Get the human-readable name for a DCID."""
        return self.dcid_to_name.get(dcid, "")

    def merge(self, other: Self) -> Self:
        """Merge another TopicStore into this one.

        For overlapping data, this store's data prevails.
        Only new data from the second store is added.
        """
        # Only add topics that don't already exist
        for topic_dcid, topic_data in other.topics_by_dcid.items():
            if topic_dcid not in self.topics_by_dcid:
                self.topics_by_dcid[topic_dcid] = topic_data

        # Merge variables (sets naturally handle duplicates)
        self.all_variables.update(other.all_variables)

        # Only add names that don't already exist
        for dcid, name in other.dcid_to_name.items():
            if dcid not in self.dcid_to_name:
                self.dcid_to_name[dcid] = name

        # Only add root topic DCIDs that don't already exist
        for dcid in other.root_topic_dcids:
            if dcid not in self.root_topic_dcids:
                self.root_topic_dcids.append(dcid)

        return self

    def debug_log(self) -> None:
        logger.info("Created topic store with %s topics", len(self.topics_by_dcid))
        for topic_dcid in self.topics_by_dcid:
            topic_data = self.topics_by_dcid[topic_dcid]
            logger.info(
                "  Topic %s: %s direct variables, %s descendant variables, %s member topics",
                topic_dcid,
                len(topic_data.member_variables),
                len(topic_data.descendant_variables),
                len(topic_data.member_topics),
            )
        logger.info("  Root topic DCIDs: %s", self.root_topic_dcids)


def _flatten_variables_recursive(
    node: Node,
    nodes_by_dcid: dict[str, Node],
    member_vars: dict[str, None],
    descendant_vars: dict[str, None],
    visited: set[str],
) -> None:
    """
    Recursively traverses the topic/svpg structure to collect unique descendant variable DCIDs.
    It uses a dictionary as an ordered set to maintain insertion order.
    """
    if node.dcid in visited:
        return
    visited.add(node.dcid)

    for child_dcid in node.children:
        child_node = nodes_by_dcid.get(child_dcid)

        if child_node:
            # We don't need to collect member variables for child nodes so we pass an empty dictionary for member_vars
            _flatten_variables_recursive(child_node, nodes_by_dcid, {}, descendant_vars, visited)
        else:
            # The child is NOT a defined node. Assume it's a variable,
            # but ignore broken topic/svpg links.
            if _DCID_PREFIX_TOPIC in child_dcid or _DCID_PREFIX_SVPG in child_dcid:
                continue
            if child_dcid not in descendant_vars:
                member_vars[child_dcid] = None
                descendant_vars[child_dcid] = None


def _is_topic_dcid(dcid: str) -> bool:
    """Check if a DCID represents a topic."""
    return "/topic/" in dcid
