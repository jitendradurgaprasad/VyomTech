"""
Unit tests for explainable priority scoring.
"""

from firewatch.config import ScoringConfig
from firewatch.data.schemas import ObservationNormalized
from firewatch.analysis.priority import PriorityRanker


def create_dummy_obs(
    obs_id: str,
    conf_norm: float = 0.8,
    frp: float = 60.0,
    acq_dt: str = "2026-10-15T12:00:00Z",
    cluster_size: int = 1,
    repeat_count: int = 0
) -> ObservationNormalized:
    return ObservationNormalized(
        id=obs_id,
        latitude=20.0,
        longitude=78.0,
        acq_date="2026-10-15",
        acq_time="1200",
        acq_datetime=acq_dt,
        satellite="Terra",
        instrument="MODIS",
        confidence_normalized=conf_norm,
        confidence_category="high" if conf_norm >= 0.8 else "nominal",
        frp=frp,
        cluster_size=cluster_size,
        repeat_detection_count=repeat_count
    )


def test_priority_ranking_deterministic():
    config = ScoringConfig()
    ranker = PriorityRanker(config)

    obs1 = create_dummy_obs("obs1", conf_norm=0.9, frp=75.0)
    obs2 = create_dummy_obs("obs2", conf_norm=0.9, frp=75.0)

    res1 = ranker.calculate_observation_priority(obs1)
    res2 = ranker.calculate_observation_priority(obs2)

    assert res1.priority_score == res2.priority_score
    assert res1.priority_level == res2.priority_level
    assert res1.priority_reasons == res2.priority_reasons


def test_priority_missing_frp_fallback():
    config = ScoringConfig()
    ranker = PriorityRanker(config)

    obs = create_dummy_obs("obs_no_frp", conf_norm=0.7, frp=None)
    res = ranker.calculate_observation_priority(obs)

    assert res.priority_score is not None
    assert 0.0 <= res.priority_score <= 1.0
    # Verify fallback limitation note is present
    has_frp_note = any("FRP data was unavailable" in l for l in res.priority_limitations)
    assert has_frp_note


def test_priority_threshold_levels():
    config = ScoringConfig(high_priority_threshold=0.70, medium_priority_threshold=0.40)
    ranker = PriorityRanker(config)

    # High priority scenario: high confidence, massive FRP, cluster size 5
    obs_high = create_dummy_obs("high", conf_norm=0.95, frp=150.0, cluster_size=5, repeat_count=4)
    res_high = ranker.calculate_observation_priority(obs_high)
    assert res_high.priority_level == "High Review Priority"

    # Low priority scenario: low confidence, minimal FRP, isolated
    obs_low = create_dummy_obs("low", conf_norm=0.20, frp=2.0, cluster_size=1, repeat_count=0)
    res_low = ranker.calculate_observation_priority(obs_low)
    assert res_low.priority_level == "Low Review Priority"


def test_priority_weight_configuration():
    # Only FRP weighted
    cfg_frp_only = ScoringConfig(
        weight_confidence=0.0,
        weight_frp=1.0,
        weight_recency=0.0,
        weight_cluster=0.0,
        weight_repeat=0.0,
        frp_reference_mw=50.0
    )
    ranker = PriorityRanker(cfg_frp_only)

    obs1 = create_dummy_obs("low_frp", frp=5.0)
    obs2 = create_dummy_obs("high_frp", frp=100.0)

    ranker.calculate_observation_priority(obs1)
    ranker.calculate_observation_priority(obs2)

    assert obs2.priority_score > obs1.priority_score
