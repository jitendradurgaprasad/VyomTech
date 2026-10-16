"""
Interactive Map Component using Folium for FireWatch AI.
"""

from __future__ import annotations
from typing import List, Optional
import os
import folium
from folium.plugins import MarkerCluster
from firewatch.data.schemas import ObservationNormalized


def _carto_tiles() -> str:
    """Return CARTO Positron tiles using the key from the private .env file."""
    key = os.getenv("CARTO_BASEMAP_API_KEY", "").strip()
    if key:
        return f"https://basemaps.cartocdn.com/rastertiles/light_all/{{z}}/{{x}}/{{y}}.png?key={key}"
    return "CartoDB positron"


CARTO_ATTRIBUTION = "© OpenStreetMap contributors © CARTO"
CARTO_MAX_NATIVE_ZOOM = 18
MAP_MAX_ZOOM = 22


def get_priority_color(level: Optional[str]) -> str:
    """Map priority level to map marker color."""
    if not level:
        return "blue"
    lvl = level.lower()
    if "high" in lvl:
        return "red"
    elif "medium" in lvl:
        return "orange"
    else:
        return "blue"


def build_folium_map(
    observations: List[ObservationNormalized],
    selected_id: Optional[str] = None,
    use_clustering: bool = True,
    max_markers: int = 1000
) -> folium.Map:
    """
    Build an interactive Folium map representing active fire observations.
    """
    # Determine center coordinates
    if observations:
        if selected_id:
            match = next((o for o in observations if o.id == selected_id), None)
            if match:
                center_lat, center_lon = match.latitude, match.longitude
                zoom_start = 9
            else:
                center_lat = sum(o.latitude for o in observations[:100]) / min(len(observations), 100)
                center_lon = sum(o.longitude for o in observations[:100]) / min(len(observations), 100)
                zoom_start = 5
        else:
            center_lat = sum(o.latitude for o in observations[:100]) / min(len(observations), 100)
            center_lon = sum(o.longitude for o in observations[:100]) / min(len(observations), 100)
            zoom_start = 5
    else:
        # Default center on South Asia
        center_lat, center_lon = 20.5937, 78.9629
        zoom_start = 4

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=zoom_start,
        tiles=None,
        max_zoom=MAP_MAX_ZOOM,
        control_scale=True
    )

    # CARTO raster endpoints stop serving native tiles above z18. Leaflet's
    # maxNativeZoom keeps requesting z18 and scales it at closer display zooms.
    folium.TileLayer(
        tiles=_carto_tiles(),
        attr=CARTO_ATTRIBUTION,
        name="CARTO Positron",
        overlay=False,
        max_zoom=MAP_MAX_ZOOM,
        max_native_zoom=CARTO_MAX_NATIVE_ZOOM,
        show=True,
    ).add_to(m)

    # Optional Esri Satellite basemap layer
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery",
        name="Satellite Imagery",
        overlay=False
    ).add_to(m)

    folium.TileLayer("OpenStreetMap", name="Standard Street Map").add_to(m)

    if not observations:
        folium.LayerControl().add_to(m)
        return m

    # Container for markers
    marker_container = MarkerCluster(name="Fire Detections") if use_clustering else folium.FeatureGroup(name="Detections")

    # Add markers (up to max_markers for UI responsiveness)
    display_obs = observations[:max_markers]
    for obs in display_obs:
        color = get_priority_color(obs.priority_level)
        is_selected = (selected_id is not None and obs.id == selected_id)
        
        frp_str = f"{obs.frp:.1f} MW" if obs.frp is not None else "Unavailable"
        bright_str = f"{obs.brightness_kelvin:.1f} K" if obs.brightness_kelvin else "N/A"
        reasons_html = "".join(f"<li>{r}</li>" for r in (obs.priority_reasons or []))

        popup_html = f"""
        <div style="font-family: Arial, sans-serif; min-width: 240px; font-size: 12px;">
            <h4 style="margin: 0 0 6px 0; color: #2c3e50;">{obs.id}</h4>
            <div style="padding: 3px 6px; border-radius: 4px; display: inline-block; font-weight: bold; margin-bottom: 8px;
                        background: {'#f8d7da; color: #721c24;' if color == 'red' else ('#fff3cd; color: #856404;' if color == 'orange' else '#d1ecf1; color: #0c5460;')}">
                {obs.priority_level or 'Unscored'} (Score: {obs.priority_score or 0.0:.4f})
            </div>
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 8px;">
                <tr><td><b>Coordinates:</b></td><td>{obs.latitude:.4f}, {obs.longitude:.4f}</td></tr>
                <tr><td><b>Acquisition:</b></td><td>{obs.acq_datetime}</td></tr>
                <tr><td><b>Satellite / Sensor:</b></td><td>{obs.satellite} ({obs.instrument})</td></tr>
                <tr><td><b>Confidence:</b></td><td>{obs.confidence_category.upper()} ({obs.confidence_normalized*100:.1f}%)</td></tr>
                <tr><td><b>FRP:</b></td><td>{frp_str}</td></tr>
                <tr><td><b>Brightness:</b></td><td>{bright_str}</td></tr>
                <tr><td><b>Cluster Size:</b></td><td>{obs.cluster_size} (Repeats: {obs.repeat_detection_count})</td></tr>
                <tr><td><b>Region:</b></td><td>{obs.administrative_region}</td></tr>
                <tr><td><b>Jurisdiction:</b></td><td>{obs.jurisdiction}</td></tr>
            </table>
            <details>
                <summary style="cursor: pointer; color: #007bff; font-weight: bold;">Triage Reasons</summary>
                <ul style="margin: 4px 0; padding-left: 18px;">
                    {reasons_html}
                </ul>
            </details>
            <div style="margin-top: 8px; font-size: 10px; color: #7f8c8d; border-top: 1px solid #ecf0f1; padding-top: 4px;">
                * Unverified satellite thermal anomaly. Not confirmed wildfire.
            </div>
        </div>
        """

        marker = folium.CircleMarker(
            location=[obs.latitude, obs.longitude],
            radius=9 if is_selected else (7 if color == "red" else 5),
            color="#000000" if is_selected else color,
            weight=3 if is_selected else 1,
            fill=True,
            fill_color=color,
            fill_opacity=0.9 if is_selected else 0.7,
            popup=folium.Popup(popup_html, max_width=320),
            tooltip=f"{obs.id} | {obs.priority_level} | FRP: {frp_str}"
        )
        marker.add_to(marker_container)

    marker_container.add_to(m)
    folium.LayerControl().add_to(m)
    return m


def build_emergency_detection_map(
    fire_info: Dict[str, Any],
    nearest_ers: Dict[str, Any],
    all_stations: Optional[List[Dict[str, Any]]] = None
) -> folium.Map:
    """
    Build an interactive emergency response map showing:
    1. The satellite acquisition frame bounding box (hotspot frame coordinates).
    2. The active fire flame marker with thermal telemetry.
    3. The highlighted nearest Emergency Response Station (ERS).
    4. The geodesic dispatch route line with distance and transit metrics.
    5. High-resolution satellite and street basemap layers.
    """
    import math

    fire_lat = float(fire_info.get("latitude", 0.0))
    fire_lon = float(fire_info.get("longitude", 0.0))
    ers_lat = float(nearest_ers.get("latitude", fire_lat + 0.15))
    ers_lon = float(nearest_ers.get("longitude", fire_lon - 0.12))

    distance_km = float(nearest_ers.get("distance_km", 0.0))
    if distance_km <= 0.0:
        # Calculate Haversine distance
        p1_lat, p1_lon = math.radians(fire_lat), math.radians(fire_lon)
        p2_lat, p2_lon = math.radians(ers_lat), math.radians(ers_lon)
        dphi = p2_lat - p1_lat
        dlam = p2_lon - p1_lon
        a = math.sin(dphi / 2.0)**2 + math.cos(p1_lat) * math.cos(p2_lat) * math.sin(dlam / 2.0)**2
        distance_km = round(6371.0088 * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a)), 2)

    center_lat = (fire_lat + ers_lat) / 2.0
    center_lon = (fire_lon + ers_lon) / 2.0

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=11,
        tiles="OpenStreetMap",
        max_zoom=MAP_MAX_ZOOM,
        control_scale=True
    )

    # High-Resolution Esri World Satellite Imagery layer
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery",
        name="Satellite Imagery (High Res)",
        overlay=False
    ).add_to(m)

    # CartoDB Positron base layer
    folium.TileLayer(_carto_tiles(), attr=CARTO_ATTRIBUTION,
                     name="CARTO Positron", overlay=False,
                     max_zoom=MAP_MAX_ZOOM,
                     max_native_zoom=CARTO_MAX_NATIVE_ZOOM).add_to(m)

    # 1. SATELLITE ACQUISITION FRAME BOUNDING BOX (Approx 1 km x 1 km sensor pixel)
    d_lat = 0.009
    d_lon = 0.009 / max(math.cos(math.radians(fire_lat)), 0.1)
    frame_bounds = [
        [fire_lat - d_lat / 2.0, fire_lon - d_lon / 2.0],
        [fire_lat + d_lat / 2.0, fire_lon + d_lon / 2.0]
    ]

    obs_id = fire_info.get("observation_id", "HOTSPOT")
    frp_val = fire_info.get("frp", "N/A")

    folium.Rectangle(
        bounds=frame_bounds,
        color="#d32f2f",
        weight=2.5,
        fill=True,
        fill_color="#ff1744",
        fill_opacity=0.35,
        tooltip=f"Satellite Sensor Frame Footprint: Hotspot {obs_id} (~1 km² Pixel)",
        popup=folium.Popup(
            f"<b>Satellite Sensor Frame Coordinates</b><br>"
            f"Center: {fire_lat:.5f}° N, {fire_lon:.5f}° E<br>"
            f"FRP Intensity: {frp_val} MW<br>"
            f"Footprint: ~1.0 km² sensor resolution",
            max_width=260
        )
    ).add_to(m)

    # 2. FIRE HOTSPOT MARKER (Red Flame Icon)
    fire_popup_html = f"""
    <div style="font-family: Arial, sans-serif; min-width: 230px; font-size: 12px;">
        <h4 style="margin: 0 0 6px 0; color: #b71c1c;">🔥 SATELLITE FIRE HOTSPOT</h4>
        <div style="padding: 3px 6px; border-radius: 4px; display: inline-block; font-weight: bold; margin-bottom: 6px; background: #f8d7da; color: #721c24;">
            Hotspot ID: {obs_id}
        </div>
        <table style="width: 100%; border-collapse: collapse; font-size: 11px;">
            <tr><td><b>Coordinates:</b></td><td><b>{fire_lat:.5f}° N, {fire_lon:.5f}° E</b></td></tr>
            <tr><td><b>Thermal FRP:</b></td><td><span style="color: #d32f2f; font-weight: bold;">{frp_val} MW</span></td></tr>
            <tr><td><b>Priority:</b></td><td>{fire_info.get('priority_level', 'High Review Priority')}</td></tr>
            <tr><td><b>Region:</b></td><td>{fire_info.get('region', 'Identified Region')}</td></tr>
        </table>
        <div style="margin-top: 6px; padding: 4px; background: #ffebee; border-left: 3px solid #d32f2f; font-size: 10px;">
            🚨 Nearest ERS Alerted: <b>{nearest_ers.get('name', 'ERS Command')}</b> ({distance_km:.1f} km away)
        </div>
    </div>
    """
    folium.Marker(
        location=[fire_lat, fire_lon],
        popup=folium.Popup(fire_popup_html, max_width=320),
        tooltip=f"🔥 FIRE HOTSPOT: {obs_id} ({fire_lat:.4f}N, {fire_lon:.4f}E | FRP: {frp_val} MW)",
        icon=folium.Icon(color="red", icon="fire", prefix="fa")
    ).add_to(m)

    # 3. NEAREST ERS LOCATION MARKER (Highlighted Dark Blue Shield Icon)
    est_transit = nearest_ers.get("est_transit_minutes", int(distance_km / 45.0 * 60) + 10)
    ers_popup_html = f"""
    <div style="font-family: Arial, sans-serif; min-width: 250px; font-size: 12px;">
        <h4 style="margin: 0 0 6px 0; color: #1565c0;">🛡️ NEAREST EMERGENCY RESPONSE STATION</h4>
        <div style="background: #e3f2fd; padding: 6px; border-radius: 4px; margin-bottom: 6px;">
            <b style="color: #0d47a1;">{nearest_ers.get('name', 'Regional ERS Station')}</b>
        </div>
        <table style="width: 100%; border-collapse: collapse; font-size: 11px;">
            <tr><td><b>Station Distance:</b></td><td><b style="color: #2e7d32; font-size: 12px;">{distance_km:.1f} km</b> to Fire Hotspot</td></tr>
            <tr><td><b>ERS Coordinates:</b></td><td>{ers_lat:.5f}° N, {ers_lon:.5f}° E</td></tr>
            <tr><td><b>Jurisdiction:</b></td><td>{nearest_ers.get('jurisdiction', 'Regional Division')}</td></tr>
            <tr><td><b>Emergency Email:</b></td><td><code>{nearest_ers.get('contact_details', 'mjdp8086@gmail.com')}</code></td></tr>
            <tr><td><b>Emergency Mobile:</b></td><td>+91-9705447958, +91-7793956633</td></tr>
            <tr><td><b>Est. Ground Transit:</b></td><td>~{est_transit} minutes</td></tr>
        </table>
        <div style="margin-top: 6px; padding: 4px; background: #e8f5e9; border-left: 3px solid #2e7d32; font-size: 10px;">
            ✉️ Mail Alert Automatically Dispatched to Station Officer
        </div>
    </div>
    """
    folium.Marker(
        location=[ers_lat, ers_lon],
        popup=folium.Popup(ers_popup_html, max_width=340),
        tooltip=f"🛡️ NEAREST ERS: {nearest_ers.get('name', 'ERS Station')} ({distance_km:.1f} km to Fire)",
        icon=folium.Icon(color="darkblue", icon="shield", prefix="fa")
    ).add_to(m)

    # 4. EMERGENCY DISPATCH ROUTE VECTOR (Dashed Red PolyLine)
    folium.PolyLine(
        locations=[[fire_lat, fire_lon], [ers_lat, ers_lon]],
        color="#d32f2f",
        weight=3.5,
        dash_array="6, 8",
        opacity=0.9,
        tooltip=f"⚡ Emergency Dispatch Vector: {distance_km:.1f} km from {nearest_ers.get('name', 'ERS Station')} to Fire Hotspot"
    ).add_to(m)

    # 5. MIDPOINT DISTANCE BADGE
    mid_lat = (fire_lat + ers_lat) / 2.0
    mid_lon = (fire_lon + ers_lon) / 2.0
    folium.map.Marker(
        [mid_lat, mid_lon],
        icon=folium.DivIcon(
            html=f"""
            <div style="
                background: rgba(211, 47, 47, 0.92);
                color: white;
                font-family: Arial, sans-serif;
                font-size: 11px;
                font-weight: bold;
                padding: 3px 8px;
                border-radius: 12px;
                border: 1.5px solid white;
                box-shadow: 0 2px 6px rgba(0,0,0,0.35);
                white-space: nowrap;
                transform: translate(-50%, -50%);
            ">
                ⚡ Dispatch: {distance_km:.1f} km (~{est_transit}m)
            </div>
            """
        )
    ).add_to(m)

    # 6. OTHER REGIONAL ERS STATIONS (Context Network)
    if all_stations:
        for oth in all_stations:
            if oth.get("id") == nearest_ers.get("id"):
                continue
            o_lat = float(oth.get("latitude", 0.0))
            o_lon = float(oth.get("longitude", 0.0))
            if abs(o_lat) < 0.1 and abs(o_lon) < 0.1:
                continue
            folium.CircleMarker(
                location=[o_lat, o_lon],
                radius=6,
                color="#1976d2",
                fill=True,
                fill_color="#90caf9",
                fill_opacity=0.85,
                tooltip=f"Regional ERS Node: {oth.get('name')}",
                popup=folium.Popup(f"<b>{oth.get('name')}</b><br>{oth.get('region')}<br>Contact: {oth.get('contact_details')}", max_width=220)
            ).add_to(m)

    # Fit bounds with padding so both markers and the frame are centered
    min_lat = min(fire_lat, ers_lat) - 0.04
    max_lat = max(fire_lat, ers_lat) + 0.04
    min_lon = min(fire_lon, ers_lon) - 0.04
    max_lon = max(fire_lon, ers_lon) + 0.04
    m.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]])

    folium.LayerControl().add_to(m)
    return m
