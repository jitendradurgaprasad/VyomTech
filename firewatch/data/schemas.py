"""
Data schemas and models for FireWatch AI.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator


class ObservationNormalized(BaseModel):
    """Normalized, validated active fire observation record."""
    id: str = Field(description="Unique deterministic observation hash ID")
    latitude: float = Field(ge=-90.0, le=90.0, description="Latitude in decimal degrees")
    longitude: float = Field(ge=-180.0, le=180.0, description="Longitude in decimal degrees")
    acq_date: str = Field(description="Acquisition date in YYYY-MM-DD")
    acq_time: str = Field(description="Acquisition time in HHMM UTC")
    acq_datetime: str = Field(description="Combined ISO 8601 UTC timestamp")
    satellite: str = Field(default="Unknown", description="Satellite platform (e.g. Terra, Aqua, Suomi-NPP, NOAA-20)")
    instrument: str = Field(default="Unknown", description="Sensor instrument (MODIS, VIIRS)")
    confidence_raw: Optional[str] = Field(default=None, description="Original confidence string or number")
    confidence_normalized: float = Field(ge=0.0, le=1.0, description="Confidence normalized to [0.0, 1.0]")
    confidence_category: str = Field(description="Confidence category: low, nominal, or high")
    brightness_kelvin: Optional[float] = Field(default=None, description="Brightness temperature (Kelvin)")
    bright_secondary: Optional[float] = Field(default=None, description="Secondary band brightness (bright_t31 or bright_ti5)")
    frp: Optional[float] = Field(default=None, ge=0.0, description="Fire Radiative Power (MW)")
    daynight: Optional[str] = Field(default=None, description="Day (D) or Night (N)")
    scan: Optional[float] = Field(default=None, description="Spatial resolution along scan (km)")
    track: Optional[float] = Field(default=None, description="Spatial resolution along track (km)")
    source_product: str = Field(default="FIRMS_GENERIC", description="Source data product name")
    
    # Priority & Clustering (populated during analysis)
    priority_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    priority_level: Optional[str] = Field(default="Unscored")
    priority_reasons: List[str] = Field(default_factory=list)
    priority_limitations: List[str] = Field(default_factory=list)
    cluster_id: Optional[int] = Field(default=-1, description="-1 indicates noise/unclustered")
    cluster_size: Optional[int] = Field(default=1)
    repeat_detection_count: Optional[int] = Field(default=0)
    
    # Geographic Context
    jurisdiction: Optional[str] = Field(default="Jurisdiction unknown")
    administrative_region: Optional[str] = Field(default="Unknown")
    
    # Preservation of raw source attributes
    raw_data: Dict[str, Any] = Field(default_factory=dict, description="Preserved exact original record attributes")


class ValidationIssue(BaseModel):
    """Detailed record of a rejected or flagged row."""
    row_number: int
    reason: str
    field: Optional[str] = None
    raw_snippet: Dict[str, Any] = Field(default_factory=dict)


class ValidationReport(BaseModel):
    """Comprehensive validation report for an ingested dataset."""
    dataset_name: str
    source_product: str
    import_timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    total_rows: int = 0
    valid_rows: int = 0
    invalid_rows: int = 0
    duplicate_rows: int = 0
    missing_field_counts: Dict[str, int] = Field(default_factory=dict)
    rejection_reasons: List[ValidationIssue] = Field(default_factory=list)
    acq_date_min: Optional[str] = None
    acq_date_max: Optional[str] = None
    attribution: str = (
        "NASA FIRMS data courtesy of NASA Earth Science Data and Information System (ESDIS) "
        "and Land, Atmosphere Near real-time Capability for EOS (LANCE). Data license: "
        "NASA Open Data Policy (public domain / open for scientific and commercial use)."
    )

    def summary_dict(self) -> Dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "source_product": self.source_product,
            "import_timestamp": self.import_timestamp,
            "total_rows": self.total_rows,
            "valid_rows": self.valid_rows,
            "invalid_rows": self.invalid_rows,
            "duplicate_rows": self.duplicate_rows,
            "acceptance_rate_pct": round((self.valid_rows / self.total_rows * 100) if self.total_rows > 0 else 0, 2),
            "date_range": f"{self.acq_date_min} to {self.acq_date_max}" if self.acq_date_min else "N/A"
        }
