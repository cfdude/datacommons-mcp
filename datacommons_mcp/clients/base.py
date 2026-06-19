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
"""Core DCClient class composing the observations, entities, and search mixins."""

from datacommons_client.client import DataCommonsClient

from datacommons_mcp._constrained_vars import place_statvar_constraint_mapping
from datacommons_mcp.cache import LruCache
from datacommons_mcp.clients.entities import _EntitiesMixin
from datacommons_mcp.clients.observations import _ObservationsMixin
from datacommons_mcp.clients.search import _SearchMixin
from datacommons_mcp.data_models.enums import SearchScope
from datacommons_mcp.topics import TopicStore


class DCClient(_ObservationsMixin, _EntitiesMixin, _SearchMixin):
    def __init__(
        self,
        dc: DataCommonsClient,
        search_scope: SearchScope = SearchScope.BASE_ONLY,
        base_index: str = "base_uae_mem",
        custom_index: str | None = None,
        sv_search_base_url: str = "https://datacommons.org",
        topic_store: TopicStore | None = None,
        _place_like_constraints: list[str] | None = None,
    ) -> None:
        """
        Initialize the DCClient with a DataCommonsClient and search configuration.

        Args:
            dc: DataCommonsClient instance
            search_scope: SearchScope enum controlling search behavior
            base_index: Index to use for base DC searches
            custom_index: Index to use for custom DC searches (None for base DC)
            sv_search_base_url: Base URL for SV search endpoint
            topic_store: Optional TopicStore for caching

            # TODO(@jm-rivera): Remove this parameter once new endpoint is live.
            _place_like_constraints: Optional list of place-like constraints
        """
        self.dc = dc
        self.search_scope = search_scope
        self.base_index = base_index
        self.custom_index = custom_index
        # Precompute search indices to validate configuration at instantiation time
        self.search_indices = self._compute_search_indices()
        self.sv_search_base_url = sv_search_base_url
        self.variable_cache = LruCache(128)

        if topic_store is None:
            topic_store = TopicStore(topics_by_dcid={}, all_variables=set())
        self.topic_store = topic_store

        if _place_like_constraints:
            self._compute_place_like_statvar_store(constraints=_place_like_constraints)
        else:
            self._place_like_statvar_store = {}

    #
    # Initialization & Configuration
    #
    def _compute_search_indices(self) -> list[str]:
        """Compute and validate search indices based on the configured search_scope.

        Raises a ValueError immediately for invalid configurations (e.g., CUSTOM_ONLY
        without a custom_index).
        """
        indices: list[str] = []

        if self.search_scope in [SearchScope.CUSTOM_ONLY, SearchScope.BASE_AND_CUSTOM]:
            if self.custom_index is not None and self.custom_index != "":
                indices.append(self.custom_index)
            elif self.search_scope == SearchScope.CUSTOM_ONLY:
                raise ValueError(
                    "Custom index not configured but CUSTOM_ONLY search scope requested"
                )

        if self.search_scope in [SearchScope.BASE_ONLY, SearchScope.BASE_AND_CUSTOM]:
            indices.append(self.base_index)

        return indices

    def _compute_place_like_statvar_store(self, constraints: list[str]) -> None:
        """Compute and cache place-like to statistical variable mappings.
        # TODO (@jm-rivera): Remove once new endpoint is live.
        """
        self._place_like_statvar_store = place_statvar_constraint_mapping(
            client=self.dc, place_like_constraints=constraints
        )
