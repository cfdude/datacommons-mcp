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

"""
Unit tests for the DCClient class.

This file tests the DCClient wrapper class from `datacommons_mcp.clients`.
It specifically mocks the underlying `datacommons_client.client.DataCommonsClient`
to ensure that our wrapper logic calls the correct methods on the underlying client
without making actual network calls.
"""

import os
from unittest.mock import AsyncMock, Mock, patch

import pytest
import requests
from datacommons_client.client import DataCommonsClient

from datacommons_mcp.clients import SURFACE_HEADER_VALUE, DCClient, create_dc_client
from datacommons_mcp.config import BaseDCSettings, CustomDCSettings
from datacommons_mcp.data_models.enums import SearchScope
from datacommons_mcp.data_models.observations import (
    ObservationDateType,
    ObservationRequest,
)
from datacommons_mcp.data_models.search import (
    NodeInfo,
    SearchResult,
    SearchTask,
    SearchTopic,
    SearchVariable,
)


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """A fixture to isolate tests from .env files and existing env vars."""
    monkeypatch.chdir(tmp_path)

    # This inner function will be the fixture's return value
    def _patch_env(env_vars):
        return patch.dict(os.environ, env_vars, clear=True)

    return _patch_env


@pytest.fixture
def mocked_datacommons_client():
    """
    Provides a mocked instance of the underlying `DataCommonsClient`.

    This fixture patches the `DataCommonsClient` constructor within the
    `datacommons_mcp.clients` module. Any instance of `DCClient` created
    in a test using this fixture will have its `self.dc` attribute set to
    this mock instance.
    """
    with patch("datacommons_mcp.clients.DataCommonsClient") as mock_constructor:
        mock_instance = Mock(spec=DataCommonsClient)
        # Manually add the client endpoints which aren't picked up by spec
        mock_instance.observation = Mock()

        mock_constructor.return_value = mock_instance
        yield mock_instance


class TestDCClientConstructor:
    """Tests for the DCClient constructor and search indices computation."""

    def test_dc_client_constructor_base_dc(self, mocked_datacommons_client):
        """
        Test base DC constructor with default parameters.
        """
        # Arrange: Create a base DC client with default parameters
        client_under_test = DCClient(dc=mocked_datacommons_client)

        # Assert: Verify the client is configured correctly
        assert client_under_test.dc == mocked_datacommons_client
        assert client_under_test.search_scope == SearchScope.BASE_ONLY
        assert client_under_test.base_index == "base_uae_mem"
        assert client_under_test.custom_index is None
        assert client_under_test.search_indices == ["base_uae_mem"]

    def test_dc_client_constructor_custom_dc(self, mocked_datacommons_client):
        """
        Test custom DC constructor with custom index.
        """
        # Arrange: Create a custom DC client with custom index
        client_under_test = DCClient(
            dc=mocked_datacommons_client,
            search_scope=SearchScope.CUSTOM_ONLY,
            base_index="medium_ft",
            custom_index="user_all_minilm_mem",
        )

        # Assert: Verify the client is configured correctly
        assert client_under_test.dc == mocked_datacommons_client
        assert client_under_test.search_scope == SearchScope.CUSTOM_ONLY
        assert client_under_test.base_index == "medium_ft"
        assert client_under_test.custom_index == "user_all_minilm_mem"
        assert client_under_test.search_indices == ["user_all_minilm_mem"]

    def test_dc_client_constructor_base_and_custom(self, mocked_datacommons_client):
        """
        Test constructor with BASE_AND_CUSTOM search scope.
        """
        # Arrange: Create a client that searches both base and custom indices
        client_under_test = DCClient(
            dc=mocked_datacommons_client,
            search_scope=SearchScope.BASE_AND_CUSTOM,
            base_index="medium_ft",
            custom_index="user_all_minilm_mem",
        )

        # Assert: Verify the client is configured correctly
        assert client_under_test.search_scope == SearchScope.BASE_AND_CUSTOM
        assert client_under_test.search_indices == ["user_all_minilm_mem", "medium_ft"]

    def test_compute_search_indices_validation_custom_only_without_index(
        self, mocked_datacommons_client
    ):
        """
        Test that CUSTOM_ONLY search scope without custom_index raises ValueError.
        """
        # Arrange & Act & Assert: Creating client with invalid configuration should raise ValueError
        with pytest.raises(
            ValueError,
            match="Custom index not configured but CUSTOM_ONLY search scope requested",
        ):
            DCClient(
                dc=mocked_datacommons_client,
                search_scope=SearchScope.CUSTOM_ONLY,
                custom_index=None,
            )

    def test_compute_search_indices_validation_custom_only_with_empty_index(
        self, mocked_datacommons_client
    ):
        """
        Test that CUSTOM_ONLY search scope with empty custom_index raises ValueError.
        """
        # Arrange & Act & Assert: Creating client with invalid configuration should raise ValueError
        with pytest.raises(
            ValueError,
            match="Custom index not configured but CUSTOM_ONLY search scope requested",
        ):
            DCClient(
                dc=mocked_datacommons_client,
                search_scope=SearchScope.CUSTOM_ONLY,
                custom_index="",
            )


class TestDCClientFetchObs:
    """Tests for the fetch_obs method of DCClient."""

    async def test_fetch_obs_calls_fetch_for_single_place(self, mocked_datacommons_client):
        """
        Verifies that fetch_obs calls the correct underlying API for a single place.
        """
        # Arrange
        client_under_test = DCClient(dc=mocked_datacommons_client)
        request = ObservationRequest(
            variable_dcid="var1",
            place_dcid="place1",
            date_type=ObservationDateType.LATEST,
            child_place_type=None,  # Explicitly None for single place query
        )

        # Act
        await client_under_test.fetch_obs(request)

        # Assert
        # Verify that the correct underlying method was called with the right parameters
        mocked_datacommons_client.observation.fetch.assert_called_once_with(
            variable_dcids="var1",
            entity_dcids="place1",
            date=ObservationDateType.LATEST,
            filter_facet_ids=None,
        )
        # Verify that the other method was not called
        mocked_datacommons_client.observation.fetch_observations_by_entity_type.assert_not_called()

    async def test_fetch_obs_calls_fetch_by_entity_type_for_child_places(
        self, mocked_datacommons_client
    ):
        """
        Verifies that fetch_obs calls the correct underlying API for child places.
        """
        # Arrange
        client_under_test = DCClient(dc=mocked_datacommons_client)
        request = ObservationRequest(
            variable_dcid="var1",
            place_dcid="parent_place",
            child_place_type="County",
            date_type=ObservationDateType.LATEST,
        )

        # Act
        await client_under_test.fetch_obs(request)

        # Assert
        # Verify that the correct underlying method was called with the right parameters
        mocked_datacommons_client.observation.fetch_observations_by_entity_type.assert_called_once_with(
            variable_dcids="var1",
            parent_entity="parent_place",
            entity_type="County",
            date=ObservationDateType.LATEST,
            filter_facet_ids=None,
        )
        # Verify that the other method was not called
        mocked_datacommons_client.observation.fetch.assert_not_called()


class TestDCClientFetchIndicatorsNew:
    """Tests for the _fetch_indicators_new method of DCClient."""

    @pytest.fixture
    def client(self, mocked_datacommons_client: Mock) -> DCClient:
        """Provides a DCClient instance for testing the new path."""
        client = DCClient(dc=mocked_datacommons_client)
        # Mock async methods that might be called
        client.fetch_entity_names = AsyncMock(return_value={})
        return client

    @pytest.mark.asyncio
    @patch("datacommons_mcp.clients.asyncio.to_thread")
    async def test_api_call_construction(self, mock_to_thread, client: DCClient):
        """
        Tests that _fetch_indicators_new constructs the API call correctly.
        """
        # Arrange
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"queryResults": []}
        mock_to_thread.return_value = mock_response

        search_tasks = [
            SearchTask(query="query1"),
            SearchTask(query="query2"),
            SearchTask(query="query1"),  # Duplicate query
        ]
        # Act
        await client._fetch_indicators_new(
            search_tasks=search_tasks, per_search_limit=15, include_topics=True
        )
        # Assert
        mock_to_thread.assert_awaited_once()
        # Check the arguments passed to requests.get via asyncio.to_thread
        # call_args[0][0] is the function (requests.get)
        # call_args[0][1] is the first arg to requests.get (the URL)
        # call_args[1] are the kwargs to requests.get
        call_args, call_kwargs = mock_to_thread.call_args
        assert call_args[1] == "https://datacommons.org/api/nl/search-indicators"
        params = call_kwargs["params"]
        # Queries should be unique and sorted
        assert params["queries"] == ["query1", "query2"]
        # Limit should be doubled
        assert params["limit_per_index"] == 30
        assert params["index"] == ["base_uae_mem"]

    @pytest.mark.asyncio
    @patch("datacommons_mcp.clients.asyncio.to_thread")
    async def test_api_error_handling(self, mock_to_thread, client: DCClient):
        """
        Tests that an API error is caught and returns empty results.
        """
        # Arrange
        mock_to_thread.side_effect = requests.exceptions.RequestException("API Error")

        # Act
        search_result, dcid_name_mappings = await client._fetch_indicators_new(
            search_tasks=[SearchTask(query="test")],
            per_search_limit=10,
            include_topics=True,
        )

        assert search_result == SearchResult()
        assert dcid_name_mappings == {}

    @pytest.mark.asyncio
    @patch("datacommons_mcp.clients.asyncio.to_thread")
    async def test_processing_flow(self, mock_to_thread, client: DCClient):
        """
        Tests that the correct internal helpers are called during processing.
        """
        # Arrange
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        # Return one topic and one variable
        mock_response.json.return_value = {
            "queryResults": [
                {
                    "query": "test",
                    "indexResults": [
                        {
                            "index": "base_uae_mem",
                            "results": [
                                {
                                    "dcid": "dc/topic/Health",
                                    "name": "Health",
                                    "typeOf": "Topic",
                                },
                                {"dcid": "Count_Person", "name": "Person Count"},
                            ],
                        }
                    ],
                }
            ]
        }
        mock_to_thread.return_value = mock_response

        # Mock the internal helper methods to act as spies
        client._filter_indicators_by_existence = Mock(side_effect=lambda indicators, _: indicators)
        client._get_topics_members_with_existence_new = Mock()
        client._expand_topics_to_variables = Mock(
            side_effect=lambda indicators, _: [
                i for i in indicators if isinstance(i, SearchVariable)
            ]
        )

        # Act
        await client._fetch_indicators_new(
            search_tasks=[SearchTask(query="test", place_dcids=["geoId/06"])],
            per_search_limit=10,
            include_topics=False,  # Set to False to trigger expand
        )

        # Assert
        # Verify that filtering and processing helpers were called
        client._filter_indicators_by_existence.assert_called_once()
        client._get_topics_members_with_existence_new.assert_called_once()
        client._expand_topics_to_variables.assert_called_once()

    @pytest.mark.asyncio
    @patch("datacommons_mcp.clients.asyncio.to_thread")
    async def test_final_name_lookup(self, mock_to_thread, client: DCClient):
        """
        Tests that missing names for topic members are fetched at the end.
        """
        # Arrange
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        # API returns a topic, but not its member
        mock_response.json.return_value = {
            "queryResults": [
                {
                    "query": "test",
                    "indexResults": [
                        {
                            "index": "base_uae_mem",
                            "results": [
                                {
                                    "dcid": "dc/topic/Health",
                                    "name": "Health",
                                    "typeOf": "Topic",
                                },
                            ],
                        }
                    ],
                }
            ]
        }
        mock_to_thread.return_value = mock_response

        # Mock topic store to define the members of the Health topic
        client.topic_store = Mock()
        health_topic_data = Mock()
        health_topic_data.member_topics = ["dc/topic/SubHealth"]  # Member topic
        health_topic_data.member_variables = ["Count_Person_Health"]  # Member variable
        client.topic_store.topics_by_dcid.get.return_value = health_topic_data

        # Mock the final name lookup to return names for the members
        client.fetch_entity_names.return_value = {
            "dc/topic/SubHealth": "Sub-Health Topic",
            "Count_Person_Health": "Health-related Person Count",
        }

        # Act
        search_result, final_dcid_name_mappings = await client._fetch_indicators_new(
            search_tasks=[SearchTask(query="test")],
            per_search_limit=10,
            include_topics=True,
        )

        # Assert
        # 1. The main topic is in the final SearchResult object
        assert "dc/topic/Health" in search_result.topics
        health_topic = search_result.topics["dc/topic/Health"]
        # 2. The members of that topic should have been populated
        assert health_topic.member_topics == ["dc/topic/SubHealth"]
        assert health_topic.member_variables == ["Count_Person_Health"]

        # 3. The final name mappings should contain the original name AND the fetched member names
        assert final_dcid_name_mappings == {
            "dc/topic/Health": "Health",
            "dc/topic/SubHealth": "Sub-Health Topic",
            "Count_Person_Health": "Health-related Person Count",
        }
        # 4. fetch_entity_names should have been called with only the missing DCIDs
        client.fetch_entity_names.assert_awaited_once_with(
            sorted(["dc/topic/SubHealth", "Count_Person_Health"])
        )

    def test_transform_response_basic_mixed_types(self, client: DCClient):
        """
        Tests transformation of a standard API response with mixed indicator types.
        """
        # Arrange
        api_response = {
            "queryResults": [
                {
                    "query": "health",
                    "indexResults": [
                        {
                            "index": "base_uae_mem",
                            "results": [
                                {
                                    "dcid": "dc/topic/Health",
                                    "name": "Health",
                                    "typeOf": "Topic",
                                },
                                {
                                    "dcid": "Count_Person",
                                    "name": "Person Count",
                                    "typeOf": "StatisticalVariable",
                                },
                            ],
                        }
                    ],
                }
            ]
        }

        # Act
        results_by_search, dcid_name_mappings = client._transform_search_indicators_response(
            api_response
        )

        # Assert
        # Check results_by_search structure
        assert "health-base_uae_mem" in results_by_search
        indicators = results_by_search["health-base_uae_mem"]
        assert len(indicators) == 2
        assert isinstance(indicators[0], SearchTopic)
        assert indicators[0].dcid == "dc/topic/Health"
        assert isinstance(indicators[1], SearchVariable)
        assert indicators[1].dcid == "Count_Person"

        # Check name mappings
        assert dcid_name_mappings == {
            "dc/topic/Health": "Health",
            "Count_Person": "Person Count",
        }

    def test_transform_response_topic_with_null_type(self, client: DCClient):
        """
        Tests that a dcid with a topic prefix is classified as a topic
        even if the typeOf field is null or missing.
        """
        # Arrange
        api_response = {
            "queryResults": [
                {
                    "query": "health",
                    "indexResults": [
                        {
                            "index": "base_uae_mem",
                            "results": [
                                {
                                    "dcid": "dc/topic/Health",
                                    "name": "Health",
                                    "typeOf": None,
                                },
                            ],
                        }
                    ],
                }
            ]
        }

        # Act
        results_by_search, dcid_name_mappings = client._transform_search_indicators_response(
            api_response
        )

        # Assert
        assert "health-base_uae_mem" in results_by_search
        indicators = results_by_search["health-base_uae_mem"]
        assert len(indicators) == 1
        assert isinstance(indicators[0], SearchTopic)
        assert indicators[0].dcid == "dc/topic/Health"
        assert dcid_name_mappings == {"dc/topic/Health": "Health"}

    def test_transform_response_orders_by_score_desc(self, client: DCClient):
        """Results within a single search are ordered by score descending (task 1.1)."""
        # Arrange: results supplied OUT of score order
        api_response = {
            "queryResults": [
                {
                    "query": "health",
                    "indexResults": [
                        {
                            "index": "base_uae_mem",
                            "results": [
                                {"dcid": "Var_Low", "name": "Low", "score": 0.10},
                                {"dcid": "Var_High", "name": "High", "score": 0.90},
                                {"dcid": "Var_Mid", "name": "Mid", "score": 0.50},
                                # Null score must not crash the sort (treated as 0.0)
                                {"dcid": "Var_Null", "name": "Null", "score": None},
                            ],
                        }
                    ],
                }
            ]
        }

        # Act
        results_by_search, _ = client._transform_search_indicators_response(api_response)

        # Assert: ordered by score descending; null score sorts last (0.0)
        dcids = [ind.dcid for ind in results_by_search["health-base_uae_mem"]]
        assert dcids == ["Var_High", "Var_Mid", "Var_Low", "Var_Null"]

    def test_transform_response_topic_by_typeof_without_prefix(self, client: DCClient):
        """A typeOf=='Topic' indicator without the topic DCID prefix is surfaced as a topic.

        The legacy shim dropped such topics (it required the prefix AND local-store
        membership); the native flow must surface them.
        """
        # Arrange: dcid has NO topic prefix, only typeOf marks it a Topic
        api_response = {
            "queryResults": [
                {
                    "query": "health",
                    "indexResults": [
                        {
                            "index": "base_uae_mem",
                            "results": [
                                {
                                    "dcid": "some/CustomTopicId",
                                    "name": "Custom Topic",
                                    "typeOf": "Topic",
                                },
                            ],
                        }
                    ],
                }
            ]
        }

        # Act
        results_by_search, _ = client._transform_search_indicators_response(api_response)

        # Assert: surfaced as a SearchTopic, not dropped
        indicators = results_by_search["health-base_uae_mem"]
        assert len(indicators) == 1
        assert isinstance(indicators[0], SearchTopic)
        assert indicators[0].dcid == "some/CustomTopicId"

    def test_transform_response_empty(self, client: DCClient):
        """Tests transformation with an empty API response."""
        api_response = {"queryResults": []}
        results_by_search, dcid_name_mappings = client._transform_search_indicators_response(
            api_response
        )
        assert results_by_search == {}
        assert dcid_name_mappings == {}

    def test_transform_response_missing_dcid(self, client: DCClient):
        """Tests that indicators missing a dcid are skipped."""
        api_response = {
            "queryResults": [
                {
                    "query": "test",
                    "indexResults": [{"index": "test_idx", "results": [{"name": "No DCID"}]}],
                }
            ]
        }
        results_by_search, dcid_name_mappings = client._transform_search_indicators_response(
            api_response
        )
        assert results_by_search == {}
        assert dcid_name_mappings == {}

    def test_transform_response_missing_name(self, client: DCClient):
        """Tests that indicators missing a name are still processed."""
        api_response = {
            "queryResults": [
                {
                    "query": "test",
                    "indexResults": [{"index": "test_idx", "results": [{"dcid": "var1"}]}],
                }
            ]
        }
        results_by_search, dcid_name_mappings = client._transform_search_indicators_response(
            api_response
        )
        assert "test-test_idx" in results_by_search
        assert len(results_by_search["test-test_idx"]) == 1
        assert results_by_search["test-test_idx"][0].dcid == "var1"
        assert dcid_name_mappings == {}  # No name was provided

    def test_transform_response_only_variables(self, client: DCClient):
        """Tests a response containing only variables."""
        api_response = {
            "queryResults": [
                {
                    "query": "vars",
                    "indexResults": [
                        {
                            "index": "idx1",
                            "results": [
                                {"dcid": "var1", "name": "Var 1"},
                                {"dcid": "var2", "name": "Var 2"},
                            ],
                        }
                    ],
                }
            ]
        }
        results_by_search, dcid_name_mappings = client._transform_search_indicators_response(
            api_response
        )
        assert "vars-idx1" in results_by_search
        indicators = results_by_search["vars-idx1"]
        assert len(indicators) == 2
        assert all(isinstance(i, SearchVariable) for i in indicators)
        assert dcid_name_mappings == {"var1": "Var 1", "var2": "Var 2"}

    def test_transform_response_only_topics(self, client: DCClient):
        """Tests a response containing only topics."""
        api_response = {
            "queryResults": [
                {
                    "query": "topics",
                    "indexResults": [
                        {
                            "index": "idx1",
                            "results": [
                                {
                                    "dcid": "topic1",
                                    "name": "Topic 1",
                                    "typeOf": "Topic",
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        results_by_search, dcid_name_mappings = client._transform_search_indicators_response(
            api_response
        )
        assert "topics-idx1" in results_by_search
        indicators = results_by_search["topics-idx1"]
        assert len(indicators) == 1
        assert isinstance(indicators[0], SearchTopic)
        assert dcid_name_mappings == {"topic1": "Topic 1"}

    def test_transform_response_multiple_queries(self, client: DCClient):
        """Tests a response with multiple query results."""
        api_response = {
            "queryResults": [
                {
                    "query": "q1",
                    "indexResults": [
                        {
                            "index": "idx1",
                            "results": [{"dcid": "var1", "name": "Var 1"}],
                        }
                    ],
                },
                {
                    "query": "q2",
                    "indexResults": [
                        {
                            "index": "idx2",
                            "results": [{"dcid": "var2", "name": "Var 2"}],
                        }
                    ],
                },
            ]
        }
        results_by_search, dcid_name_mappings = client._transform_search_indicators_response(
            api_response
        )
        assert len(results_by_search) == 2
        assert "q1-idx1" in results_by_search
        assert "q2-idx2" in results_by_search
        assert len(results_by_search["q1-idx1"]) == 1
        assert len(results_by_search["q2-idx2"]) == 1
        assert dcid_name_mappings == {"var1": "Var 1", "var2": "Var 2"}

    def test_filter_indicators_by_existence_mixed_types(self, client: DCClient):
        """
        Tests that _filter_indicators_by_existence correctly filters a mix of
        SearchTopic and SearchVariable objects.
        """
        # Arrange
        indicators = [
            SearchTopic(dcid="dc/topic/Health"),  # Has data
            SearchVariable(dcid="Count_Person"),  # Has data
            SearchTopic(dcid="dc/topic/Economy"),  # No data
            SearchVariable(dcid="Count_Household"),  # No data
        ]
        place_dcids = ["geoId/06"]

        # Mock the underlying existence check methods
        client._get_topic_places_with_data = Mock(
            side_effect=lambda dcid, _: ["geoId/06"] if dcid == "dc/topic/Health" else []
        )
        client._get_variable_places_with_data = Mock(
            side_effect=lambda dcid, _: ["geoId/06"] if dcid == "Count_Person" else []
        )

        # Act
        filtered_indicators = client._filter_indicators_by_existence(indicators, place_dcids)

        # Assert
        assert len(filtered_indicators) == 2
        filtered_dcids = {i.dcid for i in filtered_indicators}
        assert "dc/topic/Health" in filtered_dcids
        assert "Count_Person" in filtered_dcids

        # Check that places_with_data is populated
        health_topic = next(i for i in filtered_indicators if i.dcid == "dc/topic/Health")
        assert health_topic.places_with_data == ["geoId/06"]

    def test_filter_indicators_by_existence_empty_indicators(self, client: DCClient):
        """Tests filtering with an empty list of indicators."""
        result = client._filter_indicators_by_existence([], ["geoId/06"])
        assert result == []

    def test_filter_indicators_by_existence_empty_places(self, client: DCClient):
        """
        Tests that filtering with an empty list of place_dcids returns all
        indicators, as no filtering should be applied.
        """
        indicators = [
            SearchTopic(dcid="dc/topic/Health"),
            SearchVariable(dcid="Count_Person"),
        ]
        result = client._filter_indicators_by_existence(indicators, [])
        assert result == indicators
        # Verify places_with_data is not populated
        for indicator in result:
            if isinstance(indicator, SearchVariable):
                assert indicator.places_with_data == []
            else:
                assert indicator.places_with_data is None

    def test_expand_topics_to_variables_basic_expansion(self, client: DCClient):
        """
        Tests that a topic is correctly expanded into its member variables.
        """
        # Arrange
        topic = SearchTopic(dcid="dc/topic/Health")
        topic.member_variables = ["var_from_topic_1", "var_from_topic_2"]
        indicators = [
            topic,
            SearchVariable(dcid="original_var"),
        ]
        place_dcids = ["geoId/06"]

        # Mock existence check to assume all variables exist
        client._get_variable_places_with_data = Mock(return_value=place_dcids)

        # Act
        result = client._expand_topics_to_variables(indicators, place_dcids)

        # Assert
        assert len(result) == 3
        result_dcids = {v.dcid for v in result}
        assert "original_var" in result_dcids
        assert "var_from_topic_1" in result_dcids
        assert "var_from_topic_2" in result_dcids
        # The topic should no longer be present
        assert not any(isinstance(i, SearchTopic) for i in result)

    def test_expand_topics_to_variables_deduplication(self, client: DCClient):
        """
        Tests that if a topic's member variable is already in the list,
        it is not duplicated.
        """
        # Arrange
        topic = SearchTopic(dcid="dc/topic/Health")
        topic.member_variables = ["var_from_topic", "duplicate_var"]
        indicators = [
            topic,
            SearchVariable(dcid="duplicate_var"),  # Already present
        ]
        place_dcids = ["geoId/06"]

        # Mock existence check
        client._get_variable_places_with_data = Mock(return_value=place_dcids)

        # Act
        result = client._expand_topics_to_variables(indicators, place_dcids)

        # Assert
        assert len(result) == 2
        result_dcids = {v.dcid for v in result}
        assert "var_from_topic" in result_dcids
        assert "duplicate_var" in result_dcids

    def test_expand_topics_to_variables_existence_check(self, client: DCClient):
        """
        Tests that expanded variables are only included if they pass the
        existence check.
        """
        # Arrange
        topic = SearchTopic(dcid="dc/topic/Health")
        topic.member_variables = ["existing_var", "non_existing_var"]
        indicators = [topic]
        place_dcids = ["geoId/06"]

        # Mock existence: only 'existing_var' has data
        client._get_variable_places_with_data = Mock(
            side_effect=lambda dcid, _: place_dcids if dcid == "existing_var" else []
        )

        # Act
        result = client._expand_topics_to_variables(indicators, place_dcids)

        # Assert
        assert len(result) == 1
        assert result[0].dcid == "existing_var"

    def test_expand_topics_to_variables_no_place_filtering(self, client: DCClient):
        """
        Tests that expanded variables are only included if they pass the
        existence check.
        """
        # Arrange
        topic = SearchTopic(dcid="dc/topic/Health")
        topic.member_variables = ["var1", "var2"]
        indicators = [topic]

        # Act
        result = client._expand_topics_to_variables(indicators, place_dcids=[])

        # Assert
        assert len(result) == 2
        assert result[0].dcid == "var1"
        assert result[1].dcid == "var2"

    @pytest.mark.asyncio
    @patch("datacommons_mcp.clients.asyncio.to_thread")
    async def test_fetch_indicators_new_end_to_end(self, mock_to_thread, client: DCClient):
        """
        Tests the full end-to-end logic of _fetch_indicators_new, including
        API call, transformation, filtering, topic expansion, and final name lookup.
        """
        # Arrange
        # 1. Mock the API response from /api/nl/search-indicators
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "queryResults": [
                {
                    "query": "health in california",
                    "indexResults": [
                        {
                            # Results from the base index
                            "index": "base_uae_mem",
                            "results": [
                                {
                                    "dcid": "dc/topic/Health",
                                    "name": "Health",
                                    "typeOf": "Topic",
                                },
                                {
                                    "dcid": "Count_Household",
                                    "name": "Household Count",
                                },
                            ],
                        },
                        {
                            # Results from a custom index
                            "index": "custom_ft",
                            "results": [
                                {
                                    "dcid": "Count_Person",
                                    "name": "Person Count",
                                },
                                {
                                    # This is a duplicate of a result in the base index,
                                    # but it should be handled correctly.
                                    "dcid": "Count_Household",
                                    "name": "Household Count",
                                },
                            ],
                        },
                    ],
                }
            ]
        }
        mock_to_thread.return_value = mock_response

        # 2. Mock the topic store for member expansion
        client.topic_store = Mock()
        health_topic_data = Mock()
        health_topic_data.member_topics = []
        # This member variable will be added during expansion
        health_topic_data.member_variables = ["MortalityRate_Person_MedicalCondition"]
        health_topic_data.descendant_variables = ["MortalityRate_Person_MedicalCondition"]
        client.topic_store.topics_by_dcid.get.return_value = health_topic_data

        # 3. Mock the variable cache for existence checks
        # - Count_Person exists in CA
        # - Count_Household does NOT exist in CA
        # - The expanded variable from the topic exists in CA
        client.variable_cache = Mock()
        client.variable_cache.get.return_value = {
            "Count_Person",
            "MortalityRate_Person_MedicalCondition",
        }

        # 4. Mock the final name lookup for the expanded variable
        client.fetch_entity_names.return_value = {
            "MortalityRate_Person_MedicalCondition": "Mortality Rate"
        }

        search_tasks = [SearchTask(query="health in california", place_dcids=["geoId/06"])]

        # Act: Call the method with include_topics=False to trigger expansion
        search_result, dcid_name_mappings = await client._fetch_indicators_new(
            search_tasks=search_tasks,
            per_search_limit=10,
            include_topics=False,
        )

        # Assert
        # 1. Final SearchResult should contain only variables that passed existence checks
        assert search_result.topics == {}  # include_topics=False
        assert len(search_result.variables) == 2

        final_var_dcids = search_result.variables.keys()
        assert "Count_Person" in final_var_dcids
        assert "MortalityRate_Person_MedicalCondition" in final_var_dcids
        assert "Count_Household" not in final_var_dcids  # Should be filtered out

        # 2. places_with_data should be populated correctly
        assert search_result.variables["Count_Person"].places_with_data == ["geoId/06"]
        assert search_result.variables[
            "MortalityRate_Person_MedicalCondition"
        ].places_with_data == ["geoId/06"]

        # 3. Final name mappings should include names from API and the final lookup
        assert dcid_name_mappings == {
            "Count_Person": "Person Count",
            # "Count_Household" name should be filtered out as the variable was dropped
            "MortalityRate_Person_MedicalCondition": "Mortality Rate",
        }

    @pytest.mark.asyncio
    @patch("datacommons_mcp.clients.asyncio.to_thread")
    async def test_fetch_indicators_new_cross_task_merge_order(
        self, mock_to_thread, client: DCClient
    ):
        """Cross-task merge order follows the endpoint's queryResults order (Gate-2 I-1).

        Pins the contract: the endpoint is authoritative for ranking; the merge does NOT
        re-impose the legacy "task order" (the shim's place-specific-task-first behavior).
        """
        # Arrange: endpoint returns qB BEFORE qA, the reverse of search_tasks order.
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "queryResults": [
                {
                    "query": "qB",
                    "indexResults": [
                        {"index": "base_uae_mem", "results": [{"dcid": "Var_B", "name": "B"}]}
                    ],
                },
                {
                    "query": "qA",
                    "indexResults": [
                        {"index": "base_uae_mem", "results": [{"dcid": "Var_A", "name": "A"}]}
                    ],
                },
            ]
        }
        mock_to_thread.return_value = mock_response
        # No places -> no existence filtering, isolating merge order.
        search_tasks = [
            SearchTask(query="qA", place_dcids=[]),
            SearchTask(query="qB", place_dcids=[]),
        ]

        # Act
        search_result, _ = await client._fetch_indicators_new(
            search_tasks=search_tasks, per_search_limit=10, include_topics=True
        )

        # Assert: merged order follows the endpoint response (qB, qA), NOT task order (qA, qB)
        assert list(search_result.variables.keys()) == ["Var_B", "Var_A"]

    @pytest.mark.asyncio
    @patch("datacommons_mcp.clients.asyncio.to_thread")
    async def test_fetch_indicators_new_end_to_end_with_topics(
        self, mock_to_thread, client: DCClient
    ):
        """
        Tests the full end-to-end logic of _fetch_indicators_new when
        include_topics is True, ensuring topics are returned with populated members.
        """
        # Arrange
        # 1. Mock the API response from /api/nl/search-indicators
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "queryResults": [
                {
                    "query": "health in california",
                    "indexResults": [
                        {
                            "index": "base_uae_mem",
                            "results": [
                                {
                                    "dcid": "dc/topic/Health",
                                    "name": "Health",
                                    "typeOf": "Topic",
                                },
                                {
                                    "dcid": "Count_Person",
                                    "name": "Person Count",
                                },
                                {
                                    "dcid": "Count_Household",  # This will be filtered out
                                    "name": "Household Count",
                                },
                            ],
                        }
                    ],
                }
            ]
        }
        mock_to_thread.return_value = mock_response

        # 2. Mock the topic store for member population
        client.topic_store = Mock()
        health_topic_data = Mock()
        # The topic has one member variable that exists and one that does not.
        health_topic_data.member_topics = []
        health_topic_data.member_variables = [
            "MortalityRate_Person_MedicalCondition",  # Exists
            "NonExistent_Var",  # Does not exist
        ]
        client.topic_store.topics_by_dcid.get.return_value = health_topic_data

        # 3. Mock the variable cache for existence checks
        # - dc/topic/Health exists (via its member)
        # - Count_Person exists
        # - Count_Household does NOT exist
        # - MortalityRate_Person_MedicalCondition (topic member) exists
        client.variable_cache = Mock()
        client.variable_cache.get.return_value = {
            "Count_Person",
            "MortalityRate_Person_MedicalCondition",
        }

        # 4. Mock the final name lookup for the topic member variable
        client.fetch_entity_names.return_value = {
            "MortalityRate_Person_MedicalCondition": "Mortality Rate"
        }

        search_tasks = [SearchTask(query="health in california", place_dcids=["geoId/06"])]

        # Act: Call the method with include_topics=True
        search_result, dcid_name_mappings = await client._fetch_indicators_new(
            search_tasks=search_tasks,
            per_search_limit=10,
            include_topics=True,
        )

        # Assert
        # 1. Final SearchResult should contain the topic and the variable
        assert len(search_result.topics) == 1
        assert len(search_result.variables) == 1

        # 2. Check the returned topic and its populated members
        health_topic = search_result.topics["dc/topic/Health"]
        assert health_topic.places_with_data == ["geoId/06"]
        # Only the member variable that exists should be populated
        assert health_topic.member_variables == ["MortalityRate_Person_MedicalCondition"]

        # 3. Check the returned variable
        assert "Count_Person" in search_result.variables
        assert search_result.variables["Count_Person"].places_with_data == ["geoId/06"]

        # 4. Final name mappings should be correct
        assert "dc/topic/Health" in dcid_name_mappings
        assert "MortalityRate_Person_MedicalCondition" in dcid_name_mappings


class TestCreateDCClient:
    """Tests for the create_dc_client factory function."""

    @patch("datacommons_mcp.clients.DataCommonsClient")
    @patch("datacommons_mcp.clients.read_topic_caches")
    def test_create_dc_client_base_dc(
        self, mock_read_caches: Mock, mock_dc_client: Mock, isolated_env
    ):
        """Test base DC creation with defaults."""
        # Arrange
        with isolated_env({"DC_API_KEY": "test_api_key", "DC_TYPE": "base"}):
            settings = BaseDCSettings()
            mock_dc_instance = Mock()
            mock_dc_client.return_value = mock_dc_instance
            mock_read_caches.return_value = Mock()

            # Act
            result = create_dc_client(settings)

            # Assert
            assert isinstance(result, DCClient)
            assert result.dc == mock_dc_instance
            assert result.search_scope == SearchScope.BASE_ONLY
            assert result.base_index == "base_uae_mem"
            assert result.custom_index is None
            mock_dc_client.assert_called_with(
                api_key="test_api_key",
                surface_header_value=SURFACE_HEADER_VALUE,
            )

    @patch("datacommons_mcp.clients.DataCommonsClient")
    @patch("datacommons_mcp.clients.create_topic_store")
    def test_create_dc_client_custom_dc(
        self, mock_create_store: Mock, mock_dc_client: Mock, isolated_env
    ):
        """Test custom DC creation with defaults."""
        # Arrange
        env_vars = {
            "DC_API_KEY": "test_api_key",
            "DC_TYPE": "custom",
            "CUSTOM_DC_URL": "https://staging-datacommons-web-service-650536812276.northamerica-northeast1.run.app",
        }
        with isolated_env(env_vars):
            settings = CustomDCSettings()
            mock_dc_instance = Mock()
            mock_dc_client.return_value = mock_dc_instance
            mock_topic_store = Mock()
            mock_create_store.return_value = mock_topic_store

            # Act
            result = create_dc_client(settings)

            # Assert
            assert isinstance(result, DCClient)
            assert result.dc == mock_dc_instance
            assert result.search_scope == SearchScope.BASE_AND_CUSTOM
            assert result.base_index == "medium_ft"
            assert result.custom_index == "user_all_minilm_mem"
            assert (
                result.sv_search_base_url
                == "https://staging-datacommons-web-service-650536812276.northamerica-northeast1.run.app"
            )
            # Should have called DataCommonsClient with computed api_base_url
            expected_api_url = "https://staging-datacommons-web-service-650536812276.northamerica-northeast1.run.app/core/api/v2/"
            mock_dc_client.assert_called_with(
                url=expected_api_url,
                surface_header_value=SURFACE_HEADER_VALUE,
            )

    @patch("datacommons_mcp.clients.DataCommonsClient")
    def test_create_dc_client_url_computation(self, mock_dc_client):
        """Test URL computation for custom DC."""
        # Arrange
        with patch.dict(
            os.environ,
            {
                "DC_API_KEY": "test_api_key",
                "DC_TYPE": "custom",
                "CUSTOM_DC_URL": "https://example.com",  # No trailing slash
            },
        ):
            settings = CustomDCSettings()
            mock_dc_instance = Mock()
            mock_dc_client.return_value = mock_dc_instance

            # Act
            _ = create_dc_client(settings)

            # Assert
            # Should compute api_base_url by adding /core/api/v2/
            expected_api_url = "https://example.com/core/api/v2/"
            mock_dc_client.assert_called_with(
                url=expected_api_url,
                surface_header_value=SURFACE_HEADER_VALUE,
            )

    @patch("datacommons_mcp.clients.DataCommonsClient")
    @patch("datacommons_mcp.clients._create_base_topic_store")
    @patch("datacommons_mcp.clients.create_topic_store")
    @pytest.mark.parametrize(
        "test_case",
        [
            pytest.param(
                {
                    "dc_type": "base",
                    "env_vars": {"DC_API_KEY": "test_api_key", "DC_TYPE": "base"},
                    "expected_scope": SearchScope.BASE_ONLY,
                    "should_create_base": True,
                    "should_create_custom": False,
                    "should_merge": False,
                },
                id="base_only_scope_creates_only_base_topic_store",
            ),
            pytest.param(
                {
                    "dc_type": "custom",
                    "env_vars": {
                        "DC_API_KEY": "test_api_key",
                        "DC_TYPE": "custom",
                        "CUSTOM_DC_URL": "https://example.com",
                        "DC_ROOT_TOPIC_DCIDS": "topic1,topic2",
                        "DC_SEARCH_SCOPE": "custom_only",
                    },
                    "expected_scope": SearchScope.CUSTOM_ONLY,
                    "should_create_base": False,
                    "should_create_custom": True,
                    "should_merge": False,
                },
                id="custom_only_scope_creates_only_custom_topic_store",
            ),
            pytest.param(
                {
                    "dc_type": "custom",
                    "env_vars": {
                        "DC_API_KEY": "test_api_key",
                        "DC_TYPE": "custom",
                        "CUSTOM_DC_URL": "https://example.com",
                        "DC_ROOT_TOPIC_DCIDS": "topic1,topic2",
                    },
                    "expected_scope": SearchScope.BASE_AND_CUSTOM,
                    "should_create_base": True,
                    "should_create_custom": True,
                    "should_merge": True,
                },
                id="base_and_custom_scope_creates_and_merges_both_topic_stores",
            ),
        ],
    )
    def test_create_dc_client_search_scope_topic_stores(
        self,
        mock_create_store: Mock,
        mock_create_base_store: Mock,
        mock_dc_client: Mock,
        test_case: dict,
        isolated_env,
    ):
        """Test that topic store creation calls match search scope."""
        # Arrange
        env_vars = test_case["env_vars"]
        with isolated_env(env_vars):
            settings = BaseDCSettings() if test_case["dc_type"] == "base" else CustomDCSettings()
            mock_dc_instance = Mock()
            mock_dc_client.return_value = mock_dc_instance
            mock_custom_store = Mock()
            mock_base_store = Mock()
            mock_create_store.return_value = mock_custom_store
            mock_create_base_store.return_value = mock_base_store

            # Act
            result = create_dc_client(settings)

            # Assert
            assert isinstance(result, DCClient)
            assert result.search_scope == test_case["expected_scope"]

            # Verify base topic store creation
            if test_case["should_create_base"]:
                mock_create_base_store.assert_called_once_with(settings)
            else:
                mock_create_base_store.assert_not_called()

            # Verify custom topic store creation
            if test_case["should_create_custom"]:
                mock_create_store.assert_called_once_with(["topic1", "topic2"], mock_dc_instance)
            else:
                mock_create_store.assert_not_called()

            # Verify store merging
            if test_case["should_merge"]:
                mock_custom_store.merge.assert_called_once_with(mock_base_store)
            else:
                mock_custom_store.merge.assert_not_called()


class TestFetchEntityInfos:
    """Test the fetch_entity_infos method."""

    @pytest.mark.asyncio
    async def test_fetch_entity_infos(self):
        """Test successful fetch of entity information."""

        # Mock data - simple dict from dcid to name and typeOf
        mock_data = {
            "geoId/06": {"name": "California", "typeOf": ["State"]},
            "country/USA": {"name": "United States", "typeOf": ["Country"]},
        }

        # Mock the underlying DC client
        mock_dc = Mock()
        mock_response = Mock()
        mock_dc.node.fetch_property_values.return_value = mock_response

        # Mock the extract_connected_nodes method for names
        def mock_extract_connected_nodes(dcid, property_name):
            if property_name == "name" and dcid in mock_data:
                return [Mock(value=mock_data[dcid]["name"])]
            return []

        # Mock the extract_connected_dcids method for types
        def mock_extract_connected_dcids(dcid, property_name):
            if property_name == "typeOf" and dcid in mock_data:
                return mock_data[dcid]["typeOf"]
            return []

        mock_response.extract_connected_nodes.side_effect = mock_extract_connected_nodes
        mock_response.extract_connected_dcids.side_effect = mock_extract_connected_dcids

        client = DCClient(dc=mock_dc)
        result = await client.fetch_entity_infos(["geoId/06", "country/USA"])

        # Verify the entire result
        expected_result = {
            "geoId/06": NodeInfo(name="California", typeOf=["State"]),
            "country/USA": NodeInfo(name="United States", typeOf=["Country"]),
        }
        assert result == expected_result

        # Verify the underlying methods were called
        mock_dc.node.fetch_property_values.assert_called_once_with(
            node_dcids=["geoId/06", "country/USA"], properties=["name", "typeOf"]
        )
