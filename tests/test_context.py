"""
Unit tests for geographic context and jurisdiction resolution.
"""

from firewatch.analysis.context import GeoContextResolver
from firewatch.data.schemas import ObservationNormalized


def test_resolve_known_jurisdiction():
    # Mumbai / Pune coordinates (18.5204, 73.8567) -> Maharashtra
    jur, reg = GeoContextResolver.resolve_jurisdiction(18.5204, 73.8567)
    assert reg == "Maharashtra State"
    assert "Maharashtra State Forest & Emergency Division" in jur


def test_resolve_unknown_jurisdiction_no_fabrication():
    # Point in the middle of Indian Ocean (0.0, 75.0) -> Outside verified state boundaries
    jur, reg = GeoContextResolver.resolve_jurisdiction(0.0, 75.0)
    assert reg == "Unassigned Region"
    assert jur == "Jurisdiction unknown"


def test_enrich_observations():
    obs1 = ObservationNormalized(
        id="o1", latitude=18.5, longitude=73.8, acq_date="2026-10-15",
        acq_time="1200", acq_datetime="2026-10-15T12:00:00Z", confidence_normalized=0.8,
        confidence_category="high"
    )
    obs2 = ObservationNormalized(
        id="o2", latitude=50.0, longitude=10.0, acq_date="2026-10-15",
        acq_time="1200", acq_datetime="2026-10-15T12:00:00Z", confidence_normalized=0.8,
        confidence_category="high"
    )
    enriched = GeoContextResolver.enrich_observations([obs1, obs2])
    assert enriched[0].administrative_region == "Maharashtra State"
    assert enriched[1].administrative_region == "Unassigned Region"
    assert enriched[1].jurisdiction == "Jurisdiction unknown"
