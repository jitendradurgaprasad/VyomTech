"""
Unit tests for spatial clustering module.
"""

from firewatch.config import ClusteringConfig
from firewatch.data.schemas import ObservationNormalized
from firewatch.analysis.clustering import SpatialClusterer, haversine_distance_km


def test_haversine_distance():
    # New Delhi (28.6139, 77.2090) to Agra (27.1767, 78.0081) is approx 180-190 km
    dist = haversine_distance_km(28.6139, 77.2090, 27.1767, 78.0081)
    assert 170.0 < dist < 200.0


def test_spatial_clustering_groups_nearby():
    cfg = ClusteringConfig(eps_km=15.0, min_samples=2)
    clusterer = SpatialClusterer(cfg)

    # 3 points close together (< 5 km apart)
    p1 = ObservationNormalized(
        id="c1", latitude=20.000, longitude=78.000, acq_date="2026-10-15",
        acq_time="1200", acq_datetime="2026-10-15T12:00:00Z", confidence_normalized=0.8,
        confidence_category="high"
    )
    p2 = ObservationNormalized(
        id="c2", latitude=20.010, longitude=78.010, acq_date="2026-10-15",
        acq_time="1200", acq_datetime="2026-10-15T12:00:00Z", confidence_normalized=0.8,
        confidence_category="high"
    )
    # 1 isolated point far away (~500 km away)
    p3 = ObservationNormalized(
        id="iso", latitude=25.000, longitude=82.000, acq_date="2026-10-15",
        acq_time="1200", acq_datetime="2026-10-15T12:00:00Z", confidence_normalized=0.8,
        confidence_category="high"
    )

    clustered = clusterer.cluster_observations([p1, p2, p3])
    
    # p1 and p2 should have the same valid cluster_id >= 0 and size 2
    assert p1.cluster_id >= 0
    assert p1.cluster_id == p2.cluster_id
    assert p1.cluster_size == 2
    assert p2.cluster_size == 2

    # p3 should be noise (-1) with size 1
    assert p3.cluster_id == -1
    assert p3.cluster_size == 1


def test_cluster_summaries():
    cfg = ClusteringConfig(eps_km=20.0, min_samples=2)
    clusterer = SpatialClusterer(cfg)

    obs_list = [
        ObservationNormalized(
            id=f"o_{i}", latitude=20.0 + (i * 0.005), longitude=78.0 + (i * 0.005),
            acq_date="2026-10-15", acq_time="1200", acq_datetime="2026-10-15T12:00:00Z",
            confidence_normalized=0.8, confidence_category="high", frp=25.0 + i
        )
        for i in range(3)
    ]
    clusterer.cluster_observations(obs_list)
    summaries = SpatialClusterer.get_cluster_summaries(obs_list)

    assert len(summaries) == 1
    assert summaries[0]["observation_count"] == 3
    assert summaries[0]["cluster_id"] == obs_list[0].cluster_id
