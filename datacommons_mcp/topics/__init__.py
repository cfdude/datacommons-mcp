"""Topic layer for the Data Commons MCP server.

Split by concern: the in-memory model (store) and the cache/network I/O (loader).
"""

from datacommons_mcp.topics.loader import (
    create_topic_store,
    read_topic_cache,
    read_topic_caches,
)
from datacommons_mcp.topics.store import (
    Node,
    TopicNodeData,
    TopicStore,
    TopicVariables,
)

__all__ = [
    "Node",
    "TopicNodeData",
    "TopicStore",
    "TopicVariables",
    "create_topic_store",
    "read_topic_cache",
    "read_topic_caches",
]
