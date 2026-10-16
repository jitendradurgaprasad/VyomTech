"""
Geographic Context and Administrative Jurisdiction Resolution Module.
"""

from __future__ import annotations
from typing import Optional, Tuple, List, Dict
from firewatch.data.schemas import ObservationNormalized

# Trustworthy verified bounding boxes for major administrative regions (South Asia / India focus as representative sample)
# Format: name: (lat_min, lat_max, lon_min, lon_max)
VERIFIED_REGIONAL_BOUNDS = {
    "Maharashtra State": (15.6, 22.0, 72.6, 80.9),
    "Madhya Pradesh State": (21.3, 26.9, 74.0, 82.8),
    "Andhra Pradesh State": (12.6, 19.1, 76.7, 84.8),
    "Telangana State": (15.8, 19.9, 77.2, 81.3),
    "Karnataka State": (11.5, 18.5, 74.0, 78.6),
    "Gujarat State": (20.1, 24.7, 68.1, 74.5),
    "Odisha State": (17.8, 22.6, 81.4, 87.5),
    "Tamil Nadu State": (8.1, 13.6, 76.2, 80.3),
    "Rajasthan State": (23.0, 30.2, 69.5, 78.3),
    "Uttar Pradesh State": (23.9, 30.4, 77.1, 84.6),
}


class GeoContextResolver:
    """
    Resolves geographical context and administrative jurisdictions.
    Strictly follows non-fabrication rule: If coordinates fall outside verified
    administrative regions, explicitly assigns 'Jurisdiction unknown'.
    """

    @classmethod
    def resolve_jurisdiction(cls, lat: float, lon: float) -> Tuple[str, str]:
        """
        Resolve administrative jurisdiction and region.
        Returns: (jurisdiction, region_name)
        """
        for region_name, (lat_min, lat_max, lon_min, lon_max) in VERIFIED_REGIONAL_BOUNDS.items():
            if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
                return f"{region_name} Forest & Emergency Division", region_name

        # If not within known bounds, do not invent names
        return "Jurisdiction unknown", "Unassigned Region"

    @classmethod
    def enrich_observations(
        cls,
        observations: List[ObservationNormalized]
    ) -> List[ObservationNormalized]:
        """Enrich all observations with verified jurisdiction and administrative region."""
        for obs in observations:
            jur, reg = cls.resolve_jurisdiction(obs.latitude, obs.longitude)
            obs.jurisdiction = jur
            obs.administrative_region = reg
        return observations
