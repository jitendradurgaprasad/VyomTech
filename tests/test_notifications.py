"""
Unit tests for authority notification system, simulation mode, and provider abstraction.
"""

import pytest
from firewatch.config import NotificationConfig
from firewatch.storage.database import DatabaseManager
from firewatch.data.schemas import ObservationNormalized
from firewatch.notifications.manager import NotificationManager
from firewatch.notifications.providers import (
    SimulationNotificationProvider,
    SmtpNotificationProvider,
    WebhookNotificationProvider
)


@pytest.fixture
def test_setup(tmp_path):
    db_file = tmp_path / "test_notif.db"
    db = DatabaseManager(str(db_file))
    cfg = NotificationConfig(simulation_mode=True)
    manager = NotificationManager(cfg, db)
    return manager, db


def test_simulation_mode_dispatch(test_setup):
    manager, db = test_setup
    
    obs = ObservationNormalized(
        id="obs_sim_01",
        latitude=18.5204,
        longitude=73.8567,
        acq_date="2026-10-15",
        acq_time="1400",
        acq_datetime="2026-10-15T14:00:00Z",
        satellite="Terra",
        instrument="MODIS",
        confidence_normalized=0.90,
        confidence_category="high",
        priority_score=0.82,
        priority_level="High Review Priority",
        priority_reasons=["High confidence detection", "Elevated FRP"],
        priority_limitations=["Unverified satellite detection"],
        administrative_region="Maharashtra State",
        jurisdiction="Maharashtra State Forest & Emergency Division"
    )
    db.save_observations([obs])

    result = manager.process_notification(obs, trigger_reason="High priority threshold exceeded")
    
    assert result.success is True
    assert result.status == "simulated"
    assert "SIMULATION_SUCCESS" in result.provider_response

    # Verify audit record written
    logs = db.get_notification_logs()
    assert len(logs) == 1
    log_entry = logs[0]
    assert log_entry["observation_id"] == "obs_sim_01"
    assert log_entry["status"] == "simulated"


def test_duplicate_notification_throttling(test_setup):
    manager, db = test_setup
    
    obs = ObservationNormalized(
        id="obs_dup_check",
        latitude=18.5204,
        longitude=73.8567,
        acq_date="2026-10-15",
        acq_time="1400",
        acq_datetime="2026-10-15T14:00:00Z",
        satellite="Terra",
        instrument="MODIS",
        confidence_normalized=0.90,
        confidence_category="high",
        priority_score=0.85,
        priority_level="High Review Priority"
    )
    db.save_observations([obs])

    # First attempt should succeed
    res1 = manager.process_notification(obs)
    assert res1.success is True

    # Immediate second attempt should be throttled
    res2 = manager.process_notification(obs)
    assert res2.success is False
    assert "THROTTLED_DUPLICATE" in res2.provider_response


def test_notification_content_disclaimer(test_setup):
    manager, db = test_setup
    
    obs = ObservationNormalized(
        id="obs_disc_01",
        latitude=19.0,
        longitude=74.0,
        acq_date="2026-10-15",
        acq_time="1200",
        acq_datetime="2026-10-15T12:00:00Z",
        satellite="Aqua",
        instrument="MODIS",
        confidence_normalized=0.75,
        confidence_category="nominal",
        priority_score=0.65,
        priority_level="Medium Review Priority"
    )
    authority = manager.route_authority_for_observation(obs)
    subject, message, payload = manager.construct_notification_payload(obs, authority, "Rule satisfied", "alert_test")

    assert "THIS IS AN UNVERIFIED SATELLITE THERMAL DETECTION" in message
    assert "NOT A CONFIRMED WILDFIRE OR EMERGENCY DISPATCH EVENT" in message
    assert "RECOMMENDED HUMAN VERIFICATION ACTIONS" in message
    assert "https://www.openstreetmap.org/" in message


def test_smtp_provider_validation_failure():
    # Invalid host / missing credentials
    provider = SmtpNotificationProvider(host=None)
    res = provider.send_notification("invalid_email", "Subject", "Body", {})
    assert res.success is False
    assert res.status == "failed"
    assert "SMTP host is not configured" in res.error
