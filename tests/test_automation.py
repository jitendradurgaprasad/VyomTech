"""
Unit tests for Autonomous Satellite Fire Engine and Image Pipeline.
"""

import os
import pytest
from firewatch.config import AppSettings, NotificationConfig
from firewatch.storage.database import DatabaseManager
from firewatch.automation import AutonomousFireEngine
from firewatch.data.imagery import SatelliteImageryManager


@pytest.fixture
def test_engine_setup(tmp_path):
    db_file = tmp_path / "test_auto.db"
    db = DatabaseManager(str(db_file))
    cfg = AppSettings(
        database_path=str(db_file),
        notifications=NotificationConfig(
            simulation_mode=True,
            smtp_from_email="mjdp4317@gmail.com",
            emergency_receiver_email="mjdp8086@gmail.com"
        )
    )
    engine = AutonomousFireEngine(cfg, db)
    return engine, db, cfg


def test_satellite_snapshot_generation():
    # Test coordinates (lat=18.52, lon=73.85)
    img_path = SatelliteImageryManager.fetch_satellite_snapshot(
        lat=18.52,
        lon=73.85,
        obs_id="test_hotspot_img",
        zoom=10,
        frp=45.0,
        confidence_pct=90.0
    )
    assert img_path is not None
    assert os.path.exists(img_path)
    assert img_path.endswith(".jpg")


def test_autonomous_scan_and_dispatch(test_engine_setup):
    engine, db, cfg = test_engine_setup

    result = engine.run_autonomous_scan(
        source_feed="modis_south_asia_24h",
        priority_threshold=0.40,
        max_dispatches=2,
        force_dispatch=True
    )

    assert result["success"] is True
    assert result["fires_detected"] > 0
    assert len(result["dispatches"]) > 0

    first_dispatch = result["dispatches"][0]
    assert first_dispatch["sender"] == "mjdp4317@gmail.com"
    assert first_dispatch["recipient"] == "mjdp8086@gmail.com"
    assert first_dispatch["image_path"] is not None
    assert os.path.exists(first_dispatch["image_path"])

    # Verify audit log in SQLite
    logs = db.get_notification_logs()
    assert len(logs) > 0
    assert logs[0]["recipient"] == "mjdp8086@gmail.com"
