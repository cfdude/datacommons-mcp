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

from unittest.mock import AsyncMock, Mock

import pytest

from datacommons_mcp.clients import DCClient
from datacommons_mcp.data_models.observations import (
    ObservationApiResponse,
    ObservationDateType,
    ObservationToolResponse,
)
from datacommons_mcp.data_models.search import (
    NodeInfo,
    ResolvedPlace,
    SearchResponse,
    SearchTask,
    SearchTopic,
    SearchVariable,
)
from datacommons_mcp.exceptions import (
    DataLookupError,
    InvalidDateFormatError,
    InvalidDateRangeError,
    ResultTooLargeError,
)
from datacommons_mcp.services import (
    get_observations,
    get_observations_export,
    get_observations_paginated,
    search_indicators,
)
from datacommons_mcp.services.observations import (
    _validate_and_build_request,
    rank_primary_facet,
)
from datacommons_mcp.utils.output_handler import OutputHandler, OutputHandlerConfig


@pytest.mark.asyncio
class TestGetObservations:
    @pytest.fixture
    def mock_client(self):
        """
        Provides a fresh, reset mock for each test method.
        """
        mock = Mock(spec_set=DCClient)
        mock.search_places = AsyncMock()
        mock.fetch_obs = AsyncMock()
        mock.fetch_entity_infos = AsyncMock()
        mock.fetch_entity_types = AsyncMock()
        return mock

    # --- Size guardrail (item C). The guardrail lives only in get_observations_paginated
    # (the function the tool calls); the non-paginated services.get_observations used by the
    # other tests here stays unguarded, which is fine since no tool calls it. ---

    async def test_paginated_child_query_over_place_limit_is_refused(self, mock_client):
        """A child-place query spanning > max_places is refused BEFORE fetching."""
        mock_client.count_child_places = AsyncMock(return_value=3238)
        mock_client.fetch_obs_page = AsyncMock()
        with pytest.raises(ResultTooLargeError) as ei:
            await get_observations_paginated(
                client=mock_client,
                variable_dcid="Count_Person",
                place_dcid="country/USA",
                child_place_type="County",
                max_places=1000,
            )
        # Lock the actionable message content (count, limit, narrowing guidance, and the
        # sparse-variable disclosure) so a future edit can't silently drop them.
        msg = str(ei.value)
        assert "3238" in msg
        assert "DC_MAX_PLACES=1000" in msg
        assert "narrow" in msg.lower()
        assert "not only those with data" in msg
        mock_client.count_child_places.assert_awaited_once_with("country/USA", "County")
        mock_client.fetch_obs_page.assert_not_called()  # gate fires before the fetch

    async def test_paginated_child_query_at_limit_proceeds(self, mock_client):
        """At exactly the limit the query proceeds (only `>` is refused)."""
        mock_client.count_child_places = AsyncMock(return_value=1000)
        mock_client.fetch_obs_page = AsyncMock(side_effect=RuntimeError("reached fetch"))
        with pytest.raises(RuntimeError, match="reached fetch"):
            await get_observations_paginated(
                client=mock_client,
                variable_dcid="Count_Person",
                place_dcid="country/USA",
                child_place_type="County",
                max_places=1000,
            )

    async def test_paginated_child_query_under_limit_proceeds_to_fetch(self, mock_client):
        """A child-place query within the limit passes the gate and reaches the fetch."""
        mock_client.count_child_places = AsyncMock(return_value=50)
        # Use a sentinel at the fetch to prove we got past the gate without ResultTooLargeError.
        mock_client.fetch_obs_page = AsyncMock(side_effect=RuntimeError("reached fetch"))
        with pytest.raises(RuntimeError, match="reached fetch"):
            await get_observations_paginated(
                client=mock_client,
                variable_dcid="Count_Person",
                place_dcid="country/USA",
                child_place_type="County",
                max_places=1000,
            )
        mock_client.count_child_places.assert_awaited_once()

    async def test_paginated_single_place_skips_the_gate(self, mock_client):
        """A single-place query (no child_place_type) never calls the place-count gate."""
        mock_client.count_child_places = AsyncMock()
        mock_client.fetch_obs_page = AsyncMock(side_effect=RuntimeError("reached fetch"))
        with pytest.raises(RuntimeError, match="reached fetch"):
            await get_observations_paginated(
                client=mock_client,
                variable_dcid="Count_Person",
                place_dcid="country/USA",
                max_places=1,  # tiny limit, but no child_place_type -> gate skipped
            )
        mock_client.count_child_places.assert_not_called()

    async def test_input_validation_errors(self, mock_client):
        # Missing variable
        with pytest.raises(ValueError, match=r"'variable_dcid' must be specified."):
            await _validate_and_build_request(
                client=mock_client, variable_dcid="", place_name="USA"
            )

        # Missing place
        with pytest.raises(ValueError, match="Specify either 'place_name' or 'place_dcid'"):
            await _validate_and_build_request(client=mock_client, variable_dcid="var1")

    async def test_input_validation_date_validation(self, mock_client):
        # Invalid date format
        with pytest.raises(InvalidDateFormatError):
            await _validate_and_build_request(
                client=mock_client,
                variable_dcid="var1",
                place_name="USA",
                date=ObservationDateType.RANGE,
                date_range_start="2022-a",
                date_range_end="2023",
            )

        # Invalid date range
        with pytest.raises(InvalidDateRangeError):
            await _validate_and_build_request(
                client=mock_client,
                variable_dcid="var1",
                place_name="USA",
                date=ObservationDateType.RANGE,
                date_range_start="2023",
                date_range_end="2022",
            )

    async def test_request_building_with_dcids(self, mock_client):
        request = await _validate_and_build_request(
            client=mock_client, variable_dcid="var1", place_dcid="country/USA"
        )
        assert request.variable_dcid == "var1"
        assert request.place_dcid == "country/USA"
        assert request.date_type == ObservationDateType.LATEST
        mock_client.search_places.assert_not_called()

    async def test_request_building_with_resolution_success(self, mock_client):
        mock_client.search_places.return_value = {"USA": "country/USA"}

        request = await _validate_and_build_request(
            client=mock_client,
            variable_dcid="Count_Person",
            place_name="USA",
            date=ObservationDateType.RANGE,
            date_range_start="2022",
            date_range_end="2023",
        )

        mock_client.search_places.assert_awaited_once_with(["USA"])
        assert request.variable_dcid == "Count_Person"
        assert request.place_dcid == "country/USA"
        assert request.date_type == ObservationDateType.ALL
        assert request.date_filter.start_date_str == "2022-01-01"
        assert request.date_filter.end_date_str == "2023-12-31"

    async def test_request_building_with_single_date_string(self, mock_client):
        """Tests that a single date string creates a valid DateRange object."""
        mock_client.search_places.return_value = {"USA": "country/USA"}

        request = await _validate_and_build_request(
            client=mock_client,
            variable_dcid="Count_Person",
            place_name="USA",
            date="2022-05-15",
        )

        mock_client.search_places.assert_awaited_once_with(["USA"])
        assert request.variable_dcid == "Count_Person"
        assert request.place_dcid == "country/USA"
        assert request.date_type == ObservationDateType.ALL
        assert request.date_filter.start_date_str == "2022-05-15"
        assert request.date_filter.end_date_str == "2022-05-15"

    async def test_request_building_resolution_failure(self, mock_client):
        mock_client.search_places.return_value = {}  # No place found
        with pytest.raises(DataLookupError, match="DataLookupError: No place found"):
            await _validate_and_build_request(
                client=mock_client, variable_dcid="var1", place_name="invalid"
            )

    @pytest.fixture
    def mock_api_response(self):
        """Provides a mock ObservationApiResponse."""
        api_response_data = {
            "byVariable": {
                "var1": {
                    "byEntity": {
                        "country/USA": {
                            "orderedFacets": [
                                {
                                    "facetId": "source1",
                                    "observations": [
                                        {"date": "2020", "value": 10},
                                        {"date": "2021", "value": 20},
                                        {"date": "2022", "value": 30},
                                    ],
                                }
                            ]
                        },
                        "country/CAN": {
                            "orderedFacets": [
                                {
                                    "facetId": "source2",
                                    "observations": [
                                        {"date": "2021", "value": 15},
                                        {"date": "2022", "value": 25},
                                    ],
                                }
                            ]
                        },
                    }
                }
            },
            "facets": {
                "source1": {"importName": "Source One"},
                "source2": {"importName": "Source Two"},
            },
        }
        return ObservationApiResponse.model_validate(api_response_data)

    async def test_data_fetching_and_processing_get_observations_e2e_single_place(
        self, mock_client
    ):
        """Test the full get_observations flow for a single place."""
        # Arrange
        # This mock response is specific to this test and only contains data for the requested place.
        single_place_api_response_data = {
            "byVariable": {
                "var1": {
                    "metadata": {},  # Ensure metadata is present
                    "byEntity": {
                        "country/USA": {
                            "orderedFacets": [
                                {
                                    "facetId": "source1",
                                    "observations": [
                                        {"date": "2020", "value": 10},
                                        {"date": "2021", "value": 20},
                                        {"date": "2022", "value": 30},
                                    ],
                                }
                            ]
                        }
                    },
                }
            },
            "facets": {"source1": {"importName": "Source One"}},
        }
        mock_client.search_places.return_value = {"USA": "country/USA"}
        mock_client.fetch_obs.return_value = ObservationApiResponse.model_validate(
            single_place_api_response_data
        )

        mock_client.fetch_entity_names.return_value = {
            "country/USA": "United States",
            "country/CAN": "Canada",
            "var1": "Variable 1",
        }
        mock_client.fetch_entity_types.return_value = {
            "country/USA": ["Country"],
            "country/CAN": ["Country"],
        }

        # Act
        result = await get_observations(
            client=mock_client,
            variable_dcid="var1",
            place_name="USA",
            date=ObservationDateType.RANGE,
            date_range_start="2021",
            date_range_end="2022",
        )

        # Assert
        assert isinstance(result, ObservationToolResponse)
        assert result.variable.dcid == "var1"
        assert result.variable.name == "Variable 1"
        assert result.resolved_parent_place is None
        assert result.child_place_type is None

        # Check observations
        assert len(result.place_observations) == 1
        obs = result.place_observations[0]
        assert obs.place.dcid == "country/USA"
        assert obs.place.name == "United States"
        assert obs.place.type_of == ["Country"]
        assert len(obs.time_series) == 2
        assert ("2021", 20) in obs.time_series
        assert ("2022", 30) in obs.time_series

        # Check source info
        assert result.source_metadata.source_id == "source1"
        assert result.source_metadata.import_name == "Source One"
        assert len(result.alternative_sources) == 0  # No other sources for USA

    async def test_data_fetching_and_processing_get_observations_e2e_child_places(
        self, mock_client
    ):
        """Test observation retrieval for child places of a parent."""
        # Arrange
        mock_client.search_places.return_value = {"California": "country/USA/state/CA"}

        api_response_data = {
            "byVariable": {
                "var1": {
                    "byEntity": {
                        "geoId/06001": {
                            "orderedFacets": [
                                {
                                    "facetId": "source1",
                                    "observations": [{"date": "2022", "value": 100}],
                                }
                            ]
                        },
                        "geoId/06037": {
                            "orderedFacets": [
                                {
                                    "facetId": "source1",
                                    "observations": [{"date": "2022", "value": 200}],
                                }
                            ]
                        },
                        "geoId/06085": {  # Santa Clara, different source
                            "orderedFacets": [
                                {
                                    "facetId": "source2",
                                    "observations": [{"date": "2022", "value": 300}],
                                }
                            ]
                        },
                    }
                }
            },
            "facets": {
                "source1": {"importName": "Source One"},
                "source2": {"importName": "Source Two"},
            },
        }
        mock_api_response = ObservationApiResponse.model_validate(api_response_data)
        mock_client.fetch_obs.return_value = mock_api_response

        mock_client.fetch_entity_names.return_value = {
            "country/USA/state/CA": "California",
            "geoId/06001": "Alameda County",
            "geoId/06037": "Los Angeles County",
            "geoId/06085": "Santa Clara County",
        }
        mock_client.fetch_entity_types.return_value = {
            "country/USA/state/CA": ["State"],
            "geoId/06001": ["County"],
            "geoId/06037": ["County"],
            "geoId/06085": ["County"],
        }

        # Act
        result = await get_observations(
            client=mock_client,
            variable_dcid="var1",
            place_name="California",
            child_place_type="County",
            date="latest",
        )

        # Assert
        assert result.resolved_parent_place.name == "California"
        assert result.child_place_type == "County"
        # All 3 counties should be in the response
        assert len(result.place_observations) == 3

        # Check that the observations are correct
        obs_by_dcid = {obs.place.dcid: obs for obs in result.place_observations}
        # Alameda and LA have data from the primary source (source1)
        assert len(obs_by_dcid["geoId/06001"].time_series) == 1
        assert obs_by_dcid["geoId/06001"].time_series[0] == ("2022", 100.0)
        assert len(obs_by_dcid["geoId/06037"].time_series) == 1
        assert obs_by_dcid["geoId/06037"].time_series[0] == ("2022", 200.0)
        # Santa Clara has no data from source1, so its time_series is empty
        assert len(obs_by_dcid["geoId/06085"].time_series) == 0

        # Check that source2 is listed as an alternative
        assert len(result.alternative_sources) == 1
        alt_source = result.alternative_sources[0]
        assert alt_source.source_id == "source2"
        assert alt_source.places_found_count == 1

    async def test_data_fetching_unit_field(self, mock_client):
        """Tests that date='latest' fetches only the latest observation."""
        # Arrange
        mock_client.search_places.return_value = {"USA": "country/USA"}
        mock_client.fetch_obs.return_value = ObservationApiResponse.model_validate(
            {
                "byVariable": {
                    "var1": {
                        "metadata": {"unit": "USDollar"},
                        "byEntity": {
                            "country/USA": {
                                "orderedFacets": [
                                    {
                                        "facetId": "source1",
                                        "observations": [
                                            {"date": "2022", "value": 30},
                                        ],
                                    }
                                ]
                            }
                        },
                    }
                },
                "facets": {"source1": {"importName": "Source One", "unit": "USDollar"}},
            }
        )
        mock_client.fetch_entity_names.return_value = {"country/USA": "United States"}
        mock_client.fetch_entity_types.return_value = {"country/USA": ["Country"]}

        # Act
        result = await get_observations(
            client=mock_client,
            variable_dcid="var1",
            place_name="USA",
        )

        # Assert
        assert result.source_metadata.unit == "USDollar"

    async def test_data_fetching_date_filtering_date_latest(self, mock_client):
        """Tests that date='latest' fetches only the latest observation."""
        # Arrange
        mock_client.search_places.return_value = {"USA": "country/USA"}
        mock_client.fetch_obs.return_value = ObservationApiResponse.model_validate(
            {
                "byVariable": {
                    "var1": {
                        "byEntity": {
                            "country/USA": {
                                "orderedFacets": [
                                    {
                                        "facetId": "source1",
                                        "observations": [  # Only the latest observation is returned by the mock
                                            {"date": "2022", "value": 30},
                                        ],
                                    }
                                ]
                            }
                        }
                    }
                },
                "facets": {"source1": {"importName": "Source One"}},
            }
        )
        mock_client.fetch_entity_names.return_value = {"country/USA": "United States"}
        mock_client.fetch_entity_types.return_value = {"country/USA": ["Country"]}

        # Act
        result = await get_observations(
            client=mock_client,
            variable_dcid="var1",
            place_name="USA",
            date="latest",
        )

        # Assert
        assert len(result.place_observations) == 1
        obs = result.place_observations[0]
        assert len(obs.time_series) == 1
        assert obs.time_series[0] == ("2022", 30)
        # Verify the correct API call was made
        mock_client.fetch_obs.assert_called_once()
        assert mock_client.fetch_obs.call_args[0][0].date_type == ObservationDateType.LATEST

    async def test_source_selection_primary_source_selection(self, mock_client):
        """Tests that the source with data for the most places is chosen as primary."""
        # Arrange
        mock_client.search_places.return_value = {"California": "country/USA/state/CA"}
        api_response_data = {
            "byVariable": {
                "var1": {
                    "byEntity": {
                        "geoId/06001": {
                            "orderedFacets": [
                                {
                                    "facetId": "source1",
                                    "observations": [{"date": "2022", "value": 100}],
                                }
                            ]
                        },
                        "geoId/06037": {
                            "orderedFacets": [
                                {
                                    "facetId": "source1",
                                    "observations": [{"date": "2022", "value": 200}],
                                }
                            ]
                        },
                        "geoId/06085": {  # Santa Clara, different source
                            "orderedFacets": [
                                {
                                    "facetId": "source2",
                                    "observations": [{"date": "2022", "value": 300}],
                                }
                            ]
                        },
                    }
                }
            },
            "facets": {
                "source1": {"importName": "Source One"},
                "source2": {"importName": "Source Two"},
            },
        }
        mock_api_response = ObservationApiResponse.model_validate(api_response_data)
        mock_client.fetch_obs.return_value = mock_api_response
        mock_client.fetch_entity_names.return_value = {
            "country/USA/state/CA": "California",
            "geoId/06001": "Alameda County",
            "geoId/06037": "Los Angeles County",
            "geoId/06085": "Santa Clara County",
        }
        mock_client.fetch_entity_types.return_value = {
            "country/USA/state/CA": ["State"],
            "geoId/06001": ["County"],
            "geoId/06037": ["County"],
            "geoId/06085": ["County"],
        }

        # Act
        result = await get_observations(
            client=mock_client,
            variable_dcid="var1",
            place_name="California",
            child_place_type="County",
        )

        # Assert
        assert result.source_metadata.source_id == "source1"

        # Check alternative sources
        assert len(result.alternative_sources) == 1
        alt_source = result.alternative_sources[0]
        assert alt_source.source_id == "source2"
        assert alt_source.places_found_count == 1

    async def test_source_selection_single_place_with_alternative_source(self, mock_client):
        """
        Tests that for a single place response, alternative sources have
        places_found_count set to None.
        """
        # Arrange
        # Mock API response with two sources for a single place
        api_response_data = {
            "byVariable": {
                "var1": {
                    "byEntity": {
                        "country/USA": {
                            "orderedFacets": [
                                {
                                    "facetId": "source1",  # More observations, will be primary
                                    "observations": [
                                        {"date": "2021", "value": 20},
                                        {"date": "2022", "value": 30},
                                    ],
                                },
                                {
                                    "facetId": "source2",
                                    "observations": [{"date": "2022", "value": 25}],
                                },
                            ]
                        }
                    }
                }
            },
            "facets": {
                "source1": {"importName": "Source One"},
                "source2": {"importName": "Source Two"},
            },
        }
        mock_client.search_places.return_value = {"USA": "country/USA"}
        mock_client.fetch_obs.return_value = ObservationApiResponse.model_validate(
            api_response_data
        )
        mock_client.fetch_entity_names.return_value = {"country/USA": "United States"}
        mock_client.fetch_entity_types.return_value = {"country/USA": ["Country"]}

        # Act
        result = await get_observations(client=mock_client, variable_dcid="var1", place_name="USA")

        # Assert
        assert len(result.alternative_sources) == 1
        alt_source = result.alternative_sources[0]
        assert alt_source.source_id == "source2"
        assert alt_source.places_found_count is None

    async def test_source_selection_source_override(self, mock_client):
        """Tests that source_override forces the use of a specific source."""
        # Arrange
        mock_client.search_places.return_value = {"USA": "country/USA"}
        api_response_data = {
            "byVariable": {
                "var1": {
                    "byEntity": {
                        "country/USA": {
                            "orderedFacets": [
                                {
                                    "facetId": "source1",
                                    "observations": [{"date": "2022", "value": 100}],
                                },
                                {
                                    "facetId": "source2",
                                    "observations": [{"date": "2022", "value": 200}],
                                },
                            ]
                        }
                    }
                }
            },
            "facets": {
                "source1": {"importName": "Source One"},
                "source2": {"importName": "Source Two"},
            },
        }
        mock_client.fetch_obs.return_value = ObservationApiResponse.model_validate(
            api_response_data
        )
        mock_client.fetch_entity_names.return_value = {"country/USA": "United States"}
        mock_client.fetch_entity_types.return_value = {"country/USA": ["Country"]}

        # Act: Override to use source2
        result = await get_observations(
            client=mock_client,
            variable_dcid="var1",
            place_name="USA",
            source_override="source2",
        )

        # Assert
        assert result.source_metadata.source_id == "source2"
        assert result.place_observations[0].time_series[0] == ("2022", 200)
        # No alternatives should be listed when a source is selected
        assert len(result.alternative_sources) == 0

    async def test_source_selection_tiebreaker_by_facet_order(self, mock_client):
        """
        Tests that the average index in orderedFacets is used as a tie-breaker.
        Source2 should be chosen because it appears earlier on average.
        """
        # Arrange
        # source1 appears at indices 1 and 1 (avg: 1)
        # source2 appears at indices 0 and 0 (avg: 0)
        api_response_data = {
            "byVariable": {
                "var1": {
                    "byEntity": {
                        "place1": {
                            "orderedFacets": [
                                {
                                    "facetId": "source2",
                                    "observations": [{"date": "2022", "value": 1}],
                                },
                                {
                                    "facetId": "source1",
                                    "observations": [{"date": "2022", "value": 2}],
                                },
                            ]
                        },
                        "place2": {
                            "orderedFacets": [
                                {
                                    "facetId": "source2",
                                    "observations": [{"date": "2022", "value": 3}],
                                },
                                {
                                    "facetId": "source1",
                                    "observations": [{"date": "2022", "value": 4}],
                                },
                            ]
                        },
                    }
                }
            },
            "facets": {
                "source1": {"importName": "Source One"},
                "source2": {"importName": "Source Two"},
            },
        }
        mock_client.fetch_obs.return_value = ObservationApiResponse.model_validate(
            api_response_data
        )
        mock_client.fetch_entity_names.return_value = {
            "place1": "Place One",
            "place2": "Place Two",
        }
        mock_client.fetch_entity_types.return_value = {
            "place1": ["City"],
            "place2": ["City"],
        }

        # Act
        result = await get_observations(client=mock_client, variable_dcid="var1", place_dcid="any")

        # Assert
        assert result.source_metadata.source_id == "source2"

    async def test_source_selection_tiebreaker_by_source_id(self, mock_client):
        """
        Tests that the source_id is used as a final tie-breaker.
        Source2 should be chosen because it is alphabetically greater.
        """
        # Arrange
        # source1 appears at indices 0 and 1 (avg: 0.5)
        # source2 appears at indices 1 and 0 (avg: 0.5)
        api_response_data = {
            "byVariable": {
                "var1": {
                    "byEntity": {
                        "place1": {
                            "orderedFacets": [
                                {
                                    "facetId": "source1",
                                    "observations": [{"date": "2022", "value": 1}],
                                },
                                {
                                    "facetId": "source2",
                                    "observations": [{"date": "2022", "value": 2}],
                                },
                            ]
                        },
                        "place2": {
                            "orderedFacets": [
                                {
                                    "facetId": "source2",
                                    "observations": [{"date": "2022", "value": 3}],
                                },
                                {
                                    "facetId": "source1",
                                    "observations": [{"date": "2022", "value": 4}],
                                },
                            ]
                        },
                    }
                }
            },
            "facets": {
                "source1": {"importName": "Source One"},
                "source2": {"importName": "Source Two"},
            },
        }
        mock_client.fetch_obs.return_value = ObservationApiResponse.model_validate(
            api_response_data
        )
        mock_client.fetch_entity_names.return_value = {
            "place1": "Place One",
            "place2": "Place Two",
        }
        mock_client.fetch_entity_types.return_value = {
            "place1": ["City"],
            "place2": ["City"],
        }

        # Act
        result = await get_observations(client=mock_client, variable_dcid="var1", place_dcid="any")

        # Assert
        # Both have same avg rank (0.5), but source2 is alphabetically greater, so max() chooses it.
        assert result.source_metadata.source_id == "source2"

    @pytest.mark.parametrize(
        ("date1", "date2", "expected_primary_source"),
        [
            ("2022-01", "2022-02", "source2"),  # YYYY-MM
            ("2022-02", "2022-01", "source1"),  # YYYY-MM
            ("2022-01-15", "2022-01-16", "source2"),  # YYYY-MM-DD
            ("2022", "2022-06", "source2"),  # YYYY vs YYYY-MM
            ("2022-06", "2022", "source1"),  # YYYY-MM vs YYYY
            ("2022-01-16", "2022-01-15", "source1"),  # YYYY-MM-DD
            ("2022-02", "2022-01-15", "source1"),  # Mixed Granularity
        ],
    )
    async def test_source_selection_primary_source_tiebreaker_by_latest_date(
        self, mock_client, date1, date2, expected_primary_source
    ):
        """
        Tests that the latest date is used as a tie-breaker when place and
        observation counts are equal, across various date formats.
        """
        # Arrange
        # Two sources, each with one place and one observation.
        # The only difference is the date of the observation.
        api_response_data = {
            "byVariable": {
                "var1": {
                    "byEntity": {
                        "geoId/01": {  # Place 1
                            "orderedFacets": [
                                {
                                    "facetId": "source1",
                                    "observations": [{"date": date1, "value": 100}],
                                }
                            ]
                        },
                        "geoId/02": {  # Place 2
                            "orderedFacets": [
                                {
                                    "facetId": "source2",
                                    "observations": [{"date": date2, "value": 200}],
                                }
                            ]
                        },
                    }
                }
            },
            "facets": {
                "source1": {"importName": "Source One"},
                "source2": {"importName": "Source Two"},
            },
        }
        mock_client.search_places.return_value = {"USA": "country/USA"}
        mock_client.fetch_obs.return_value = ObservationApiResponse.model_validate(
            api_response_data
        )
        mock_client.fetch_entity_names.return_value = {
            "country/USA": "USA",
            "geoId/01": "Place 1",
            "geoId/02": "Place 2",
        }
        mock_client.fetch_entity_types.return_value = {
            "country/USA": ["Country"],
            "geoId/01": ["State"],
            "geoId/02": ["State"],
        }

        # Act
        result = await get_observations(
            client=mock_client,
            variable_dcid="var1",
            place_name="USA",
            child_place_type="State",
        )

        # Assert
        assert result.source_metadata.source_id == expected_primary_source


@pytest.mark.asyncio
def _search_response(*, topics=None, variables=None, names=None):
    """Build a SearchResponse as returned by client.search_indicators (names/topics/variables only)."""
    return SearchResponse(
        status="SUCCESS",
        dcid_name_mappings=names or {},
        topics=topics or [],
        variables=variables or [],
    )


class TestSearchIndicators:
    """Tests for the search_indicators service function.

    The service delegates result-finding to ``client.search_indicators`` (which returns
    topics/variables/name mappings) and then resolves PLACE metadata via
    ``client.fetch_entity_infos`` to rebuild ``dcid_place_type_mappings`` and
    ``resolved_parent_place``. These tests assert that wiring: the search tasks the
    service constructs and the response contract it preserves. Result finding,
    existence filtering, and dedup are the client's responsibility (covered by
    TestDCClientFetchIndicatorsNew).
    """

    @pytest.mark.asyncio
    async def test_browse_mode_basic(self):
        """No places: one task, result passes through, no place lookup."""
        mock_client = Mock()
        mock_client.search_indicators = AsyncMock(return_value=_search_response())
        mock_client.fetch_entity_infos = AsyncMock(return_value={})

        result = await search_indicators(client=mock_client, query="health")

        assert result.status == "SUCCESS"
        assert result.topics == []
        assert result.variables == []
        mock_client.search_indicators.assert_awaited_once()
        kwargs = mock_client.search_indicators.call_args.kwargs
        assert kwargs["search_tasks"] == [SearchTask(query="health", place_dcids=[])]
        assert kwargs["per_search_limit"] == 10
        assert kwargs["include_topics"] is True
        # No places -> no place-metadata lookup
        mock_client.fetch_entity_infos.assert_not_called()

    @pytest.mark.asyncio
    async def test_with_places_preserves_full_contract(self):
        """Topics/variables pass through; place types + names rebuilt from fetch_entity_infos (PLACES only)."""
        mock_client = Mock()
        mock_client.search_places = AsyncMock(return_value={"France": "country/FRA"})
        mock_client.search_indicators = AsyncMock(
            return_value=_search_response(
                topics=[SearchTopic(dcid="topic/trade")],
                variables=[SearchVariable(dcid="TradeExports_FRA")],
                names={"topic/trade": "Trade", "TradeExports_FRA": "Exports to France"},
            )
        )
        mock_client.fetch_entity_infos = AsyncMock(
            return_value={"country/FRA": NodeInfo(name="France", typeOf=["Country"])}
        )

        result = await search_indicators(client=mock_client, query="trade", places=["France"])

        assert [t.dcid for t in result.topics] == ["topic/trade"]
        assert [v.dcid for v in result.variables] == ["TradeExports_FRA"]
        # Names merged: indicator names (from client) + place names (from fetch_entity_infos)
        assert result.dcid_name_mappings["topic/trade"] == "Trade"
        assert result.dcid_name_mappings["country/FRA"] == "France"
        # Place type-mappings rebuilt for the query place (contractual field)
        assert result.dcid_place_type_mappings == {"country/FRA": ["Country"]}
        # fetch_entity_infos called with PLACE dcids ONLY (not topic/variable dcids)
        mock_client.fetch_entity_infos.assert_awaited_once()
        assert set(mock_client.fetch_entity_infos.call_args[0][0]) == {"country/FRA"}
        # The search task carries the resolved place dcid
        assert mock_client.search_indicators.call_args.kwargs["search_tasks"] == [
            SearchTask(query="trade", place_dcids=["country/FRA"])
        ]

    @pytest.mark.asyncio
    async def test_custom_per_search_limit_passed_through(self):
        mock_client = Mock()
        mock_client.search_indicators = AsyncMock(return_value=_search_response())
        mock_client.fetch_entity_infos = AsyncMock(return_value={})

        await search_indicators(client=mock_client, query="health", per_search_limit=5)

        assert mock_client.search_indicators.call_args.kwargs["per_search_limit"] == 5

    @pytest.mark.asyncio
    async def test_per_search_limit_validation(self):
        mock_client = Mock()
        mock_client.search_indicators = AsyncMock(return_value=_search_response())
        mock_client.fetch_entity_infos = AsyncMock(return_value={})

        with pytest.raises(ValueError, match="per_search_limit must be between 1 and 100"):
            await search_indicators(client=mock_client, query="health", per_search_limit=0)
        with pytest.raises(ValueError, match="per_search_limit must be between 1 and 100"):
            await search_indicators(client=mock_client, query="health", per_search_limit=101)

        # Valid boundary values should not raise
        await search_indicators(client=mock_client, query="health", per_search_limit=1)
        await search_indicators(client=mock_client, query="health", per_search_limit=100)

    @pytest.mark.asyncio
    async def test_exclude_topics(self):
        mock_client = Mock()
        mock_client.search_places = AsyncMock(return_value={"USA": "country/USA"})
        mock_client.search_indicators = AsyncMock(
            return_value=_search_response(
                variables=[
                    SearchVariable(dcid="Count_Person"),
                    SearchVariable(dcid="Count_Household"),
                ],
                names={"Count_Person": "Population", "Count_Household": "Households"},
            )
        )
        mock_client.fetch_entity_infos = AsyncMock(
            return_value={"country/USA": NodeInfo(name="USA", typeOf=["Country"])}
        )

        result = await search_indicators(
            client=mock_client, query="health", places=["USA"], include_topics=False
        )

        assert [v.dcid for v in result.variables] == ["Count_Person", "Count_Household"]
        assert mock_client.search_indicators.call_args.kwargs["include_topics"] is False

    @pytest.mark.asyncio
    async def test_exclude_topics_no_places(self):
        mock_client = Mock()
        mock_client.search_indicators = AsyncMock(
            return_value=_search_response(
                variables=[SearchVariable(dcid="Count_Person")],
                names={"Count_Person": "Population"},
            )
        )
        mock_client.fetch_entity_infos = AsyncMock(return_value={})

        result = await search_indicators(client=mock_client, query="health", include_topics=False)

        assert result.topics == []
        assert [v.dcid for v in result.variables] == ["Count_Person"]
        assert result.status == "SUCCESS"
        kwargs = mock_client.search_indicators.call_args.kwargs
        assert kwargs["search_tasks"] == [SearchTask(query="health", place_dcids=[])]
        assert kwargs["include_topics"] is False

    @pytest.mark.asyncio
    async def test_places_build_single_task(self):
        """places=[...] builds a single task carrying all resolved place dcids."""
        mock_client = Mock()
        mock_client.search_places = AsyncMock(
            return_value={"USA": "country/USA", "Canada": "country/CAN", "Mexico": "country/MEX"}
        )
        mock_client.search_indicators = AsyncMock(return_value=_search_response())
        mock_client.fetch_entity_infos = AsyncMock(return_value={})

        result = await search_indicators(
            client=mock_client, query="trade exports", places=["USA", "Canada", "Mexico"]
        )

        assert result.status == "SUCCESS"
        mock_client.search_places.assert_awaited_with(["USA", "Canada", "Mexico"])
        assert mock_client.search_indicators.call_args.kwargs["search_tasks"] == [
            SearchTask(
                query="trade exports",
                place_dcids=["country/USA", "country/CAN", "country/MEX"],
            )
        ]

    @pytest.mark.asyncio
    async def test_maybe_bilateral_builds_per_place_tasks(self):
        """maybe_bilateral builds one task per place (query rewritten) + the original, all carrying every place dcid."""
        mock_client = Mock()
        mock_client.search_places = AsyncMock(
            return_value={"USA": "country/USA", "France": "country/FRA"}
        )
        mock_client.search_indicators = AsyncMock(return_value=_search_response())
        mock_client.fetch_entity_infos = AsyncMock(return_value={})

        result = await search_indicators(
            client=mock_client,
            query="trade exports",
            places=["USA", "France"],
            maybe_bilateral=True,
        )

        assert result.status == "SUCCESS"
        both = ["country/USA", "country/FRA"]
        assert mock_client.search_indicators.call_args.kwargs["search_tasks"] == [
            SearchTask(query="trade exports USA", place_dcids=both),
            SearchTask(query="trade exports France", place_dcids=both),
            SearchTask(query="trade exports", place_dcids=both),
        ]

    @pytest.mark.asyncio
    async def test_maybe_bilateral_false_builds_single_task(self):
        mock_client = Mock()
        mock_client.search_places = AsyncMock(
            return_value={"USA": "country/USA", "France": "country/FRA"}
        )
        mock_client.search_indicators = AsyncMock(return_value=_search_response())
        mock_client.fetch_entity_infos = AsyncMock(return_value={})

        result = await search_indicators(
            client=mock_client, query="test", places=["USA", "France"], maybe_bilateral=False
        )

        assert result.status == "SUCCESS"
        tasks = mock_client.search_indicators.call_args.kwargs["search_tasks"]
        assert tasks == [SearchTask(query="test", place_dcids=["country/USA", "country/FRA"])]

    @pytest.mark.asyncio
    async def test_with_parent_place(self):
        """parent_place is resolved and excluded from query tasks; place types + resolved parent rebuilt."""
        mock_client = Mock()
        mock_client.search_places = AsyncMock(
            return_value={"USA": "country/USA", "California": "geoId/06", "Texas": "geoId/48"}
        )
        mock_client.search_indicators = AsyncMock(
            return_value=_search_response(
                variables=[SearchVariable(dcid="Count_Person")],
                names={"Count_Person": "Population"},
            )
        )
        mock_client.fetch_entity_infos = AsyncMock(
            return_value={
                "country/USA": NodeInfo(name="United States", typeOf=["Country"]),
                "geoId/06": NodeInfo(name="California", typeOf=["State"]),
                "geoId/48": NodeInfo(name="Texas", typeOf=["State"]),
            }
        )

        result = await search_indicators(
            client=mock_client,
            query="population",
            places=["California", "Texas"],
            parent_place="USA",
        )

        assert result.resolved_parent_place == ResolvedPlace(
            dcid="country/USA", name="United States", type_of=["Country"]
        )
        # Place type-mappings cover the query places (parent excluded from query tasks)
        assert result.dcid_place_type_mappings == {
            "geoId/06": ["State"],
            "geoId/48": ["State"],
        }
        # The search task carries the child place dcids only (parent excluded)
        assert mock_client.search_indicators.call_args.kwargs["search_tasks"] == [
            SearchTask(query="population", place_dcids=["geoId/06", "geoId/48"])
        ]
        # fetch_entity_infos called with query places + parent
        assert set(mock_client.fetch_entity_infos.call_args[0][0]) == {
            "geoId/06",
            "geoId/48",
            "country/USA",
        }

    @pytest.mark.asyncio
    async def test_parent_place_no_places_raises(self):
        mock_client = Mock()
        with pytest.raises(
            ValueError,
            match=r"`places` must be specified when `parent_place` is provided.",
        ):
            await search_indicators(client=mock_client, query="population", parent_place="USA")


def _obs_response(facet_obs_by_place: dict, facets: dict) -> ObservationApiResponse:
    """Build an ObservationApiResponse from {place: {facet_id: [(date, value), ...]}}."""
    by_entity = {}
    for place, fmap in facet_obs_by_place.items():
        ordered = [
            {"facetId": fid, "observations": [{"date": d, "value": v} for d, v in obs]}
            for fid, obs in fmap.items()
        ]
        by_entity[place] = {"orderedFacets": ordered}
    return ObservationApiResponse.model_validate(
        {"byVariable": {"Count_Person": {"byEntity": by_entity}}, "facets": facets}
    )


class TestFacetReduction:
    """Item A-i: auto facet-reduction for big child-place date='all' exports."""

    @pytest.fixture
    def mock_client(self):
        mock = Mock(spec_set=DCClient)
        mock.count_child_places = AsyncMock(return_value=3)
        mock.fetch_entity_names = AsyncMock(
            return_value={
                "Count_Person": "Population",
                "parent": "Parent",
                "pA": "A",
                "pB": "B",
                "pC": "C",
            }
        )
        mock.fetch_entity_types = AsyncMock(return_value={"parent": ["Country"]})
        return mock

    def test_rank_primary_facet_picks_coverage_winner(self):
        var = _obs_response(
            {"pA": {"s1": [("2020", 1)]}, "pB": {"s1": [("2020", 2)]}, "pC": {"s2": [("2020", 3)]}},
            {"s1": {"importName": "S1"}, "s2": {"importName": "S2"}},
        ).byVariable["Count_Person"]
        primary, counts = rank_primary_facet(var, None)
        assert primary == "s1"  # covers 2 places vs s2's 1
        assert counts == {"s1": 2, "s2": 1}

    def test_rank_coverage_tie_breaks_by_latest_date(self):
        # Both s1, s2 cover 2 places with 1 latest obs each (obs-count tiebreak degenerates
        # at date=latest) -> later latest-date wins. Pins the documented A-i tiebreak.
        var = _obs_response(
            {
                "pA": {"s1": [("2020", 1)], "s2": [("2021", 1)]},
                "pB": {"s1": [("2020", 1)], "s2": [("2021", 1)]},
            },
            {"s1": {}, "s2": {}},
        ).byVariable["Count_Person"]
        primary, _ = rank_primary_facet(var, None)
        assert primary == "s2"

    @pytest.mark.asyncio
    async def test_auto_reduction_probes_filters_and_carries_probe_forward(self, mock_client):
        # Probe (latest, multi-facet): pC has ONLY the non-primary source s2.
        probe = _obs_response(
            {
                "pA": {"s1": [("2022", 10)]},
                "pB": {"s1": [("2022", 20)]},
                "pC": {"s2": [("2022", 30)]},
            },
            {"s1": {"importName": "S1"}, "s2": {"importName": "S2"}},
        )
        # Filtered (all dates, s1 only): pC is OMITTED (it has no s1).
        filtered = _obs_response(
            {
                "pA": {"s1": [("2020", 1), ("2021", 2), ("2022", 10)]},
                "pB": {"s1": [("2020", 3), ("2022", 20)]},
            },
            {"s1": {"importName": "S1"}},
        )
        mock_client.fetch_obs_page = AsyncMock(side_effect=[(probe, None), (filtered, None)])

        resp, req, _ = await get_observations_paginated(
            client=mock_client,
            variable_dcid="Count_Person",
            place_dcid="parent",
            child_place_type="County",
            date="all",
            max_places=5000,
        )

        # Two fetches: cheap latest probe, then the filtered full fetch to the primary.
        assert mock_client.fetch_obs_page.await_count == 2
        assert req.source_ids == ["s1"]
        places = {po.place.dcid: po for po in resp.place_observations}
        # C1: pC (only non-primary) is preserved with an EMPTY series (reconstructed from probe).
        assert set(places) == {"pA", "pB", "pC"}
        assert places["pC"].time_series == []
        # ...and its name/type come from the probe-fed metadata (pins metadata carry-forward).
        assert places["pC"].place.name == "C"
        # Deterministic, API-ordered place list (not set-ordered).
        assert [po.place.dcid for po in resp.place_observations] == ["pA", "pB", "pC"]
        assert len(places["pA"].time_series) == 3  # full series from the filtered fetch
        # C2: alternative_sources carries the non-primary source from the probe.
        assert any(a.source_id == "s2" for a in resp.alternative_sources)

    @pytest.mark.asyncio
    async def test_no_probe_when_guardrail_refuses(self, mock_client):
        mock_client.count_child_places = AsyncMock(return_value=10_000)
        mock_client.fetch_obs_page = AsyncMock()
        with pytest.raises(ResultTooLargeError):
            await get_observations_paginated(
                client=mock_client,
                variable_dcid="Count_Person",
                place_dcid="parent",
                child_place_type="County",
                date="all",
                max_places=5000,
            )
        mock_client.fetch_obs_page.assert_not_called()  # probe runs AFTER the guardrail

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"place_dcid": "pA", "date": "all"},  # single place (no child_place_type)
            {
                "place_dcid": "parent",
                "child_place_type": "County",
                "date": "all",
                "source_override": "s1",
            },
            {"place_dcid": "parent", "child_place_type": "County", "date": "latest"},
            {"place_dcid": "parent", "child_place_type": "County", "date": "2020"},  # single date
            {
                "place_dcid": "parent",
                "child_place_type": "County",
                "date": "range",
                "date_range_start": "2000",
                "date_range_end": "2010",
            },
        ],
    )
    async def test_no_probe_for_unreduced_paths(self, mock_client, kwargs):
        full = _obs_response({"pA": {"s1": [("2020", 1)]}}, {"s1": {"importName": "S1"}})
        mock_client.fetch_obs_page = AsyncMock(return_value=(full, None))
        await get_observations_paginated(
            client=mock_client, variable_dcid="Count_Person", max_places=5000, **kwargs
        )
        assert mock_client.fetch_obs_page.await_count == 1  # no probe

    def test_place_budget_and_shard_defaults(self):
        from datacommons_mcp.config import AppConfig

        # A-ii raised the ceiling (now a shard trigger) and added shard knobs.
        assert AppConfig.model_fields["max_places"].default == 150000
        assert AppConfig.model_fields["shard_size"].default == 15000
        assert AppConfig.model_fields["shard_min"].default == 1000
        assert AppConfig.model_fields["shard_facet_min_coverage"].default == 0.8

    def test_shard_threshold_validator(self):
        import pytest as _pytest

        from datacommons_mcp.config import AppConfig

        # shard_min <= shard_size <= max_places must hold.
        with _pytest.raises(ValueError, match="DC_SHARD_MIN <= DC_SHARD_SIZE <= DC_MAX_PLACES"):
            AppConfig(dc_api_key="k", shard_size=200000, max_places=150000)


def _size_error(status: int = 502):
    """Build a DCStatusError mimicking the API's HTTP 500/502 size-wall responses."""
    from datacommons_client.utils.error_handling import DCStatusError

    return DCStatusError(Mock(status_code=status))


class TestPlaceSharding:
    """Item A-ii: shard large child-place exports into batches written to one CSV."""

    def _client(self, dcids, fetch_impl):
        c = Mock(spec_set=DCClient)
        c.fetch_child_place_dcids = AsyncMock(return_value=dcids)
        c.fetch_observations_by_entity_dcid = AsyncMock(side_effect=fetch_impl)
        c.fetch_entity_names = AsyncMock(return_value={})
        c.fetch_entity_types = AsyncMock(return_value={})
        return c

    async def _export(self, client, tmp_path, **overrides):
        from pathlib import Path  # noqa: F401 (kept local; assertions import as needed)

        handler = OutputHandler(client, OutputHandlerConfig(storage_dir=tmp_path))
        params = {
            "variable_dcid": "Count_Person",
            "place_dcid": "country/USA",
            "child_place_type": "County",
            "date": "all",
            "output_mode": "file",
            "output_format": "csv",
            "multi_file": False,
            "max_places": 150000,
            "shard_size": 10,
            "shard_min": 2,
            "facet_min_coverage": 0.8,
        }
        params.update(overrides)
        return await get_observations_export(client, handler, **params)

    @pytest.mark.asyncio
    async def test_sharded_export_writes_all_shards(self, tmp_path):
        from pathlib import Path

        dcids = [f"geoId/{i:05d}" for i in range(25)]  # 25 > shard_size 10 -> 3 shards

        async def _fetch(variable_dcid, entity_dcids, date, filter_facet_ids):
            return _obs_response(
                {d: {"s1": [("2020", 1.0)]} for d in entity_dcids}, {"s1": {"importName": "S1"}}
            )

        client = self._client(dcids, _fetch)
        result = await self._export(client, tmp_path)

        assert result.output_mode == "file"
        assert Path(result.file_path).exists()
        assert result.rows_written == 25  # 25 places x 1 obs each
        assert result.pages_fetched == 3  # 3 shards written into one CSV
        assert result.places_missing == 0
        client.fetch_child_place_dcids.assert_awaited_once()  # enumerated exactly once (I2)

    @pytest.mark.asyncio
    async def test_refuses_over_max_places(self, tmp_path):
        client = self._client(["x"] * 200, AsyncMock())
        with pytest.raises(ResultTooLargeError, match="DC_MAX_PLACES=150"):
            await self._export(client, tmp_path, max_places=150)

    @pytest.mark.asyncio
    async def test_under_shard_size_uses_single_path(self, tmp_path, monkeypatch):
        client = self._client(["x"] * 5, AsyncMock())  # 5 <= shard_size 10 -> not sharded

        async def _sentinel(*a, **k):
            raise RuntimeError("single path reached")

        monkeypatch.setattr(
            "datacommons_mcp.services.observations.get_observations_paginated", _sentinel
        )
        with pytest.raises(RuntimeError, match="single path reached"):
            await self._export(client, tmp_path)
        client.fetch_observations_by_entity_dcid.assert_not_called()

    @pytest.mark.asyncio
    async def test_adaptive_halving_recovers(self, tmp_path):
        dcids = [f"geoId/{i}" for i in range(10)]  # 10 > shard_size 8 -> shards [8, 2]

        async def _fetch(variable_dcid, entity_dcids, date, filter_facet_ids):
            # The latest probe (no filter) always succeeds; a filtered shard fails when >4.
            if filter_facet_ids and len(entity_dcids) > 4:
                raise _size_error(502)
            return _obs_response({d: {"s1": [("2020", 1.0)]} for d in entity_dcids}, {"s1": {}})

        client = self._client(dcids, _fetch)
        result = await self._export(client, tmp_path, shard_size=8, shard_min=2)
        assert result.rows_written == 10  # 8-shard failed -> halved 4+4 -> all 10 written

    @pytest.mark.asyncio
    async def test_floor_shard_failure_errors(self, tmp_path):
        dcids = [f"geoId/{i}" for i in range(10)]

        async def _fetch(variable_dcid, entity_dcids, date, filter_facet_ids):
            if filter_facet_ids:  # every filtered shard fails, even at the floor
                raise _size_error(500)
            return _obs_response({d: {"s1": [("2020", 1.0)]} for d in entity_dcids}, {"s1": {}})

        client = self._client(dcids, _fetch)
        with pytest.raises(ResultTooLargeError, match="DC_SHARD_MIN"):
            await self._export(client, tmp_path, shard_size=8, shard_min=8)

    @pytest.mark.asyncio
    async def test_coverage_guard_counts_places_missing(self, tmp_path):
        dcids = [f"geoId/{i:05d}" for i in range(20)]  # 20 > shard_size 10 -> 2 shards

        async def _fetch(variable_dcid, entity_dcids, date, filter_facet_ids):
            # Filtered shards return only 7 of each 10 requested (3 lack the primary).
            kept = entity_dcids[:7] if filter_facet_ids else entity_dcids
            return _obs_response({d: {"s1": [("2020", 1.0)]} for d in kept}, {"s1": {}})

        client = self._client(dcids, _fetch)
        result = await self._export(client, tmp_path, shard_size=10, facet_min_coverage=0.8)
        # 7/10 covered (< 0.8) per shard -> 3 missing each; 2 shards -> 6 (denominator = len(shard)).
        assert result.places_missing == 6
        assert "6" in result.summary

    @pytest.mark.asyncio
    async def test_one_facet_reused_across_shards(self, tmp_path):
        dcids = [f"geoId/{i:05d}" for i in range(25)]
        seen_filters = []

        async def _fetch(variable_dcid, entity_dcids, date, filter_facet_ids):
            seen_filters.append(filter_facet_ids)
            if filter_facet_ids is None:  # the probe sees all facets
                return _obs_response(
                    {d: {"s1": [("2020", 1.0)], "s2": [("2019", 1.0)]} for d in entity_dcids},
                    {"s1": {}, "s2": {}},
                )
            return _obs_response({d: {"s1": [("2020", 1.0)]} for d in entity_dcids}, {"s1": {}})

        client = self._client(dcids, _fetch)
        await self._export(client, tmp_path)
        assert seen_filters[0] is None  # probe first (all facets)
        assert all(f == ["s1"] for f in seen_filters[1:])  # every shard reuses the primary
