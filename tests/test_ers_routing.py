"""
Unit tests for Emergency Response Station (ERS) Locator and Geodesic Routing.
"""

import pytest
from firewatch.analysis.ers import ERSLocator, BENCHMARK_ERS_STATIONS
from firewatch.ui.map_view import build_emergency_detection_map


def test_ers_directory_loaded():
    stations = ERSLocator.get_all_stations()
    assert len(stations) >= len(BENCHMARK_ERS_STATIONS)
    assert any("Dhanbad" in s["name"] or "Bokaro" in s["name"] for s in stations)
    assert all("latitude" in s and "longitude" in s for s in stations)


def test_find_nearest_ers_known_region():
    # Dhanbad hotspot coordinates: 23.7644 N, 86.4052 E
    fire_lat = 23.7644
    fire_lon = 86.4052

    nearest = ERSLocator.find_nearest_ers(fire_lat, fire_lon)
    assert nearest is not None
    assert "distance_km" in nearest
    assert nearest["distance_km"] < 20.0  # Dhanbad ERS is ~4.5 km away!
    assert "Dhanbad" in nearest["name"] or "Bokaro" in nearest["name"]
    assert nearest["contact_details"] == "mjdp8086@gmail.com"


def test_find_nearest_ers_remote_synthesis():
    # Arbitrary coordinates far from Indian stations (e.g. Pacific ocean or international remote)
    fire_lat = 55.0
    fire_lon = -120.0

    nearest = ERSLocator.find_nearest_ers(fire_lat, fire_lon)
    assert nearest is not None
    assert nearest["is_synthesized"] is True
    assert nearest["distance_km"] > 0.0
    assert nearest["contact_details"] == "mjdp8086@gmail.com"


def test_build_emergency_detection_map():
    fire_info = {
        "observation_id": "test_obs_map_001",
        "latitude": 23.7644,
        "longitude": 86.4052,
        "frp": 25.5,
        "priority_level": "High Review Priority",
        "region": "Jharkhand"
    }
    nearest_ers = {
        "id": "ers_test",
        "name": "Dhanbad Regional Command",
        "latitude": 23.7957,
        "longitude": 86.4304,
        "distance_km": 4.5,
        "jurisdiction": "Eastern Forest Fire Command",
        "contact_details": "mjdp8086@gmail.com",
        "est_transit_minutes": 15
    }

    m = build_emergency_detection_map(fire_info, nearest_ers)
    assert m is not None
    html_repr = m.get_root().render()
    assert "test_obs_map_001" in html_repr
    assert "Dhanbad Regional Command" in html_repr
