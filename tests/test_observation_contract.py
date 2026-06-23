"""Contract test guarding the Data Commons observation facet-lineage mapping.

The observation lineage shown in CSV exports is mapped from upstream facet
metadata into `FacetMetadata` via Pydantic aliases that all default to None
(see datacommons_mcp/data_models/observations.py). That is a silent-failure
surface: if an upstream field is renamed (or our alias is broken in a refactor),
the lineage columns quietly go blank instead of raising.

This test pins that mapping against the saved live-API sample
(docs/audits/api-samples/v2-observation.json) so a regression fails loudly.
Refresh the sample (see docs/audits/2026-06-08-live-api-analysis.md) when
bumping `datacommons-client`.
"""

import json
from pathlib import Path

import pytest

from datacommons_mcp.data_models.observations import FacetMetadata

# Integration tier: exercises the real alias mapping against a captured live-API
# payload (no mocks) — not a fast isolated unit test.
pytestmark = pytest.mark.integration

_SAMPLE = (
    Path(__file__).resolve().parent.parent
    / "docs"
    / "audits"
    / "api-samples"
    / "v2-observation.json"
)

# Facet known (in the captured sample) to carry all four lineage fields.
_FULLY_POPULATED_FACET = "4181918134"


def _load_facets() -> dict[str, dict]:
    payload = json.loads(_SAMPLE.read_text())
    facets = payload.get("facets")
    assert facets, "sample is missing the top-level 'facets' map"
    return facets


def test_sample_fixture_exists() -> None:
    assert _SAMPLE.is_file(), f"missing observation contract fixture: {_SAMPLE}"


def test_every_facet_parses_into_facet_metadata() -> None:
    """Parsing the live payload through FacetMetadata must not raise."""
    facets = _load_facets()
    for facet_id, facet in facets.items():
        FacetMetadata.model_validate({"source_id": facet_id, **facet})


def test_always_present_lineage_fields_map_for_every_facet() -> None:
    """import_name and provenance_url are present on every facet in the sample;
    if an alias breaks, these go None and the lineage columns silently blank."""
    facets = _load_facets()
    for facet_id, facet in facets.items():
        meta = FacetMetadata.model_validate({"source_id": facet_id, **facet})
        assert meta.import_name is not None, f"import_name unmapped for facet {facet_id}"
        assert meta.provenance_url is not None, f"provenance_url unmapped for facet {facet_id}"


def test_fully_populated_facet_maps_all_lineage_fields() -> None:
    """A facet carrying all four fields must map all four (guards every alias)."""
    facets = _load_facets()
    assert _FULLY_POPULATED_FACET in facets, (
        f"expected fully-populated facet {_FULLY_POPULATED_FACET} in sample; "
        "refresh _FULLY_POPULATED_FACET if the fixture was regenerated"
    )
    meta = FacetMetadata.model_validate(
        {"source_id": _FULLY_POPULATED_FACET, **facets[_FULLY_POPULATED_FACET]}
    )
    assert meta.import_name is not None
    assert meta.measurement_method is not None
    assert meta.observation_period is not None
    assert meta.provenance_url is not None


def test_optional_lineage_fields_are_only_asserted_where_present() -> None:
    """Document that measurement_method / observation_period are legitimately
    absent on some facets — mapping correctness, not field presence, is the
    contract. Asserts the round-trip equals the source value where provided."""
    facets = _load_facets()
    checked = 0
    for facet_id, facet in facets.items():
        meta = FacetMetadata.model_validate({"source_id": facet_id, **facet})
        if "measurementMethod" in facet:
            assert meta.measurement_method == facet["measurementMethod"]
            checked += 1
        if "observationPeriod" in facet:
            assert meta.observation_period == facet["observationPeriod"]
            checked += 1
    assert checked > 0, "expected at least one optional lineage field in the sample"


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
