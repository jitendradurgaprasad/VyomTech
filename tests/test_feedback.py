"""
Unit tests for feedback workflow and SQLite audit history.
"""

import os
import pytest
from firewatch.storage.database import DatabaseManager
from firewatch.data.schemas import ObservationNormalized


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_feedback.db"
    db = DatabaseManager(str(db_file))
    return db


def test_save_and_retrieve_feedback(temp_db):
    # Setup observation
    obs = ObservationNormalized(
        id="obs_test_101",
        latitude=19.123,
        longitude=73.456,
        acq_date="2026-10-15",
        acq_time="1200",
        acq_datetime="2026-10-15T12:00:00Z",
        satellite="Aqua",
        instrument="MODIS",
        confidence_normalized=0.85,
        confidence_category="high"
    )
    temp_db.save_observations([obs])

    # First review
    rev1 = temp_db.save_review(
        observation_id="obs_test_101",
        reviewer_id="analyst_jane",
        status="Likely fire; additional verification needed",
        assessment_confidence="medium",
        notes="High thermal anomaly visible near crop boundary."
    )
    assert rev1["observation_id"] == "obs_test_101"
    assert rev1["is_correction"] is False

    # Second review (correction)
    rev2 = temp_db.save_review(
        observation_id="obs_test_101",
        reviewer_id="senior_analyst_raj",
        status="Confirmed fire based on available evidence",
        assessment_confidence="high",
        notes="Corroborated by local agricultural burn reports."
    )
    assert rev2["is_correction"] is True

    # Retrieve history
    history = temp_db.get_reviews_for_observation("obs_test_101")
    assert len(history) == 2
    # Most recent should be first
    assert history[0]["reviewer_id"] == "senior_analyst_raj"
    assert history[1]["reviewer_id"] == "analyst_jane"

    # Verify original observation record was NOT modified or corrupted
    obs_retrieved = temp_db.get_observation_by_id("obs_test_101")
    assert obs_retrieved is not None
    assert obs_retrieved.latitude == 19.123
    assert obs_retrieved.satellite == "Aqua"
