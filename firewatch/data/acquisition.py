"""
Data acquisition module for NASA FIRMS active-fire observations.
"""

from __future__ import annotations
import os
import io
import time
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
import requests

FIRMS_DIRECT_URLS = {
    "modis_south_asia_24h": "https://firms.modaps.eosdis.nasa.gov/data/active_fire/modis-c6.1/csv/MODIS_C6_1_South_Asia_24h.csv",
    "viirs_south_asia_24h": "https://firms.modaps.eosdis.nasa.gov/data/active_fire/suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_South_Asia_24h.csv",
    "modis_global_24h": "https://firms.modaps.eosdis.nasa.gov/data/active_fire/modis-c6.1/csv/MODIS_C6_1_Global_24h.csv",
    "viirs_global_24h": "https://firms.modaps.eosdis.nasa.gov/data/active_fire/suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_Global_24h.csv",
}

NASA_FIRMS_ATTRIBUTION = (
    "We acknowledge the use of data and imagery from LANCE FIRMS operated by NASA's Earth Science "
    "Data and Information System (ESDIS) with funding provided by NASA/HQ. "
    "Citation: NASA FIRMS (Fire Information for Resource Management System). Available at: "
    "https://firms.modaps.eosdis.nasa.gov/"
)


class DataAcquisitionResult:
    def __init__(
        self,
        success: bool,
        content: Optional[str] = None,
        source_name: str = "",
        records_count: int = 0,
        error: Optional[str] = None,
        attribution: str = NASA_FIRMS_ATTRIBUTION,
        timestamp: Optional[str] = None
    ):
        self.success = success
        self.content = content
        self.source_name = source_name
        self.records_count = records_count
        self.error = error
        self.attribution = attribution
        self.timestamp = timestamp or datetime.utcnow().isoformat() + "Z"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "source_name": self.source_name,
            "records_count": self.records_count,
            "error": self.error,
            "attribution": self.attribution,
            "timestamp": self.timestamp
        }


class FIRMSAcquisitionManager:
    """Manages downloading and caching real NASA FIRMS data and sample files."""

    @staticmethod
    def get_api_key_instructions() -> str:
        return (
            "To access the live NASA FIRMS REST API services:\n"
            "1. Visit https://firms.modaps.eosdis.nasa.gov/api/map_key/\n"
            "2. Enter your email to receive a free, instant 32-character MAP_KEY.\n"
            "3. Set the environment variable: FIRMS_MAP_KEY=your_key_here\n"
            "4. Alternatively, use FIRMS public near-real-time CSV feeds or local CSV uploads."
        )

    @classmethod
    def fetch_live_feed(
        cls,
        feed_key: str = "modis_south_asia_24h",
        timeout: int = 15
    ) -> DataAcquisitionResult:
        """Fetch real-time CSV data directly from NASA FIRMS public feeds."""
        url = FIRMS_DIRECT_URLS.get(feed_key)
        if not url:
            return DataAcquisitionResult(
                success=False,
                error=f"Unknown feed key: {feed_key}. Available: {list(FIRMS_DIRECT_URLS.keys())}"
            )

        try:
            headers = {"User-Agent": "FireWatch-AI-Research/1.0 (Earth Observation Triage)"}
            start_t = time.time()
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            
            text = resp.text.strip()
            lines = [l for l in text.split("\n") if l.strip()]
            records_count = max(0, len(lines) - 1)  # subtracting header

            return DataAcquisitionResult(
                success=True,
                content=text,
                source_name=feed_key,
                records_count=records_count
            )
        except requests.exceptions.RequestException as e:
            return DataAcquisitionResult(
                success=False,
                source_name=feed_key,
                error=f"HTTP Request failed for {url}: {str(e)}"
            )

    @classmethod
    def fetch_api_area(
        cls,
        map_key: str,
        source: str = "VIIRS_SNPP_NRT",
        area_bbox: str = "68,6,97,37", # South Asia approx bbox: lon_min,lat_min,lon_max,lat_max
        day_range: int = 1,
        timeout: int = 20
    ) -> DataAcquisitionResult:
        """Fetch data using NASA FIRMS API (requires MAP_KEY)."""
        if not map_key or map_key.strip() == "":
            return DataAcquisitionResult(
                success=False,
                error="NASA FIRMS MAP_KEY is not configured. " + cls.get_api_key_instructions()
            )
        
        # FIRMS API format: /api/area/csv/[MAP_KEY]/[SOURCE]/[BBOX]/[DAYS]
        api_url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{map_key.strip()}/{source}/{area_bbox}/{day_range}"
        try:
            headers = {"User-Agent": "FireWatch-AI-API/1.0"}
            resp = requests.get(api_url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            text = resp.text.strip()
            
            # Check for API error response (FIRMS often returns text with error description)
            if "Invalid Map Key" in text or "Bad Request" in text:
                return DataAcquisitionResult(
                    success=False,
                    source_name=f"API_{source}",
                    error=f"FIRMS API Error: {text}"
                )

            lines = [l for l in text.split("\n") if l.strip()]
            records_count = max(0, len(lines) - 1)
            return DataAcquisitionResult(
                success=True,
                content=text,
                source_name=f"FIRMS_API_{source}",
                records_count=records_count
            )
        except requests.exceptions.RequestException as e:
            return DataAcquisitionResult(
                success=False,
                source_name=f"FIRMS_API_{source}",
                error=f"API request failed: {str(e)}"
            )

    @classmethod
    def load_local_sample(cls, filename: str) -> DataAcquisitionResult:
        """Load a sample CSV file stored in the data directory."""
        sample_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "sample")
        filepath = os.path.join(sample_dir, filename)
        
        if not os.path.exists(filepath):
            # Try relative path
            filepath = os.path.join("data", "sample", filename)
        
        if not os.path.exists(filepath):
            return DataAcquisitionResult(
                success=False,
                error=f"Sample file not found at {filepath}"
            )
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            lines = [l for l in content.strip().split("\n") if l.strip()]
            records_count = max(0, len(lines) - 1)
            return DataAcquisitionResult(
                success=True,
                content=content,
                source_name=filename,
                records_count=records_count
            )
        except Exception as e:
            return DataAcquisitionResult(
                success=False,
                source_name=filename,
                error=f"Failed to read local sample file: {str(e)}"
            )
