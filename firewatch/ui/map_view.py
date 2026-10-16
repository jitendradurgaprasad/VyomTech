"""
Interactive Map Component using Folium for FireWatch AI.
"""

from __future__ import annotations
from typing import List, Optional
import folium
from folium.plugins import MarkerCluster
from firewatch.data.schemas import ObservationNormalized


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
        tiles="CartoDB positron",
        control_scale=True
    )

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
