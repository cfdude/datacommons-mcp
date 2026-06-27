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
"""Observation-fetching mixin for DCClient."""

from datacommons_mcp.data_models.observations import (
    ObservationApiResponse,
    ObservationDateType,
    ObservationRequest,
)

# Type for raw paginated API response
PaginatedApiResponse = tuple[ObservationApiResponse, str | None]  # (response, next_token)


class _ObservationsMixin:
    """Observation fetch + pagination methods for DCClient."""

    async def fetch_obs(self, request: ObservationRequest) -> ObservationApiResponse:
        # Get the raw API response
        if request.child_place_type:
            return self.dc.observation.fetch_observations_by_entity_type(
                variable_dcids=request.variable_dcid,
                parent_entity=request.place_dcid,
                entity_type=request.child_place_type,
                date=request.date_type,
                filter_facet_ids=request.source_ids,
            )
        return self.dc.observation.fetch(
            variable_dcids=request.variable_dcid,
            entity_dcids=request.place_dcid,
            date=request.date_type,
            filter_facet_ids=request.source_ids,
        )

    async def fetch_obs_page(
        self,
        request: ObservationRequest,
        page_token: str | None = None,
    ) -> PaginatedApiResponse:
        """
        Fetch a single page of observations with pagination support.

        This method wraps the underlying Data Commons API call and extracts
        the next_token from the response for pagination.

        Args:
            request: The observation request parameters.
            page_token: Optional token from a previous response for continuation.

        Returns:
            A tuple of (ObservationApiResponse, next_token).
            next_token is None if this is the last page.

        Note:
            The Data Commons REST V2 API returns a `nextToken` field in the
            response when there are more pages available. This method extracts
            that token for use in subsequent requests.
        """
        # Build base parameters
        params = {
            "variable_dcids": request.variable_dcid,
            "date": request.date_type,
            "filter_facet_ids": request.source_ids,
        }

        # Add page token if provided
        if page_token:
            params["page_token"] = page_token

        # Make the API call
        if request.child_place_type:
            response = self.dc.observation.fetch_observations_by_entity_type(
                parent_entity=request.place_dcid,
                entity_type=request.child_place_type,
                **params,
            )
        else:
            response = self.dc.observation.fetch(
                entity_dcids=request.place_dcid,
                **params,
            )

        # Extract next_token from raw response if available
        # The datacommons_client library wraps the response, so we need to
        # check if the underlying raw response has a nextToken field
        next_token = self._extract_next_token(response)

        return response, next_token

    async def fetch_observations_by_entity_dcid(
        self,
        variable_dcid: str,
        entity_dcids: list[str],
        date: ObservationDateType | str,
        filter_facet_ids: list[str] | None = None,
    ) -> ObservationApiResponse:
        """Fetch observations for an explicit list of entity DCIDs (a shard).

        Uses the POST-body ``entity_dcids`` path (no URL-length limit — carries tens of
        thousands of DCIDs) and composes with ``filter_facet_ids`` for facet reduction.
        Used by place-sharding to query batches of child places.
        """
        return self.dc.observation.fetch_observations_by_entity_dcid(
            variable_dcids=variable_dcid,
            entity_dcids=entity_dcids,
            date=date,
            filter_facet_ids=filter_facet_ids,
        )

    def _extract_next_token(self, response: ObservationApiResponse) -> str | None:
        """
        Extract the next page token from an observation API response.

        The Data Commons REST V2 API includes a `nextToken` field in the
        response body when more pages are available.

        Args:
            response: The ObservationApiResponse from the API.

        Returns:
            The next page token, or None if no more pages.
        """
        # The datacommons_client library wraps responses in an ObservationResponse
        # object. We need to check if the underlying data has a nextToken.
        # This depends on how the library exposes the raw response.

        # Try to access raw response data
        if hasattr(response, "_raw_response"):
            raw = response._raw_response
            if isinstance(raw, dict):
                return raw.get("nextToken")

        # Fallback: check if response has a nextToken attribute
        if hasattr(response, "next_token"):
            return response.next_token

        # Check the response's to_dict() method if available
        if hasattr(response, "to_dict"):
            response_dict = response.to_dict()
            if isinstance(response_dict, dict):
                return response_dict.get("nextToken")

        return None
