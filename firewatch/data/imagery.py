"""
Satellite Imagery Acquisition & Snapshot Generator for FireWatch AI.
"""

from __future__ import annotations
import math
import os
import io
from typing import Optional, Tuple
import requests
from PIL import Image, ImageDraw, ImageFont


def deg2num(lat_deg: float, lon_deg: float, zoom: int) -> Tuple[int, int]:
    """Convert latitude, longitude to Slippy tile numbers at specified zoom level."""
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return xtile, ytile


class SatelliteImageryManager:
    """Fetches satellite optical imagery and renders annotated snapshot overlays."""

    SNAPSHOT_DIR = os.path.join("data", "snapshots")

    @classmethod
    def ensure_dir(cls):
        os.makedirs(cls.SNAPSHOT_DIR, exist_ok=True)

    @classmethod
    def fetch_satellite_snapshot(
        cls,
        lat: float,
        lon: float,
        obs_id: str,
        zoom: int = 12,
        frp: Optional[float] = None,
        confidence_pct: Optional[float] = None,
        timeout: int = 10
    ) -> Optional[str]:
        """
        Fetch satellite imagery centered on detection coordinates and annotate with crosshair/telemetry.
        Saves to data/snapshots/{obs_id}.jpg and returns the file path.
        """
        cls.ensure_dir()
        target_path = os.path.join(cls.SNAPSHOT_DIR, f"{obs_id}.jpg")
        
        # Check if already cached
        if os.path.exists(target_path):
            return target_path

        xtile, ytile = deg2num(lat, lon, zoom)
        tile_url = f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{zoom}/{ytile}/{xtile}"
        headers = {"User-Agent": "FireWatch-AI-Satellite-Vision/1.0"}

        try:
            resp = requests.get(tile_url, headers=headers, timeout=timeout)
            resp.raise_for_status()

            base_img = Image.open(io.BytesIO(resp.content)).convert("RGB")
            
            # Annotate with thermal anomaly indicator
            draw = ImageDraw.Draw(base_img)
            w, h = base_img.size
            cx, cy = w // 2, h // 2

            # Red target circle & crosshair
            radius = 16
            draw.ellipse(
                [(cx - radius, cy - radius), (cx + radius, cy + radius)],
                outline="#FF0000",
                width=3
            )
            draw.line([(cx - radius - 8, cy), (cx + radius + 8, cy)], fill="#FF3333", width=2)
            draw.line([(cx, cy - radius - 8), (cx, cy + radius + 8)], fill="#FF3333", width=2)

            # Telemetry text banner at the top
            banner_h = 28
            draw.rectangle([(0, 0), (w, banner_h)], fill=(0, 0, 0, 180))
            
            frp_text = f"FRP: {frp:.1f} MW" if frp is not None else "FRP: N/A"
            conf_text = f"Conf: {confidence_pct:.0f}%" if confidence_pct is not None else ""
            info_str = f"SATELLITE FIRE OBSERVATION: {frp_text} {conf_text}"
            coord_str = f"{lat:.4f}, {lon:.4f} (Zoom {zoom})"
            
            draw.text((6, 4), info_str, fill="#FFFF00")
            draw.text((6, 16), coord_str, fill="#FFFFFF")

            base_img.save(target_path, "JPEG", quality=90)
            return target_path
        except Exception:
            # Fallback: Generate a clean synthetic satellite placeholder if network offline
            try:
                placeholder = Image.new("RGB", (256, 256), color=(30, 45, 30))
                draw = ImageDraw.Draw(placeholder)
                draw.rectangle([(0, 0), (256, 30)], fill=(10, 20, 10))
                draw.text((10, 8), f"FIRE HOTSPOT: {lat:.4f}, {lon:.4f}", fill="#FFFF00")
                draw.ellipse([(112, 112), (144, 144)], outline="#FF0000", width=3)
                placeholder.save(target_path, "JPEG")
                return target_path
            except Exception:
                return None
