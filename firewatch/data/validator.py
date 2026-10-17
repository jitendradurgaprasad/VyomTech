"""
CSV Validation and Normalization Pipeline for NASA FIRMS Observations.
"""

from __future__ import annotations
import hashlib
import io
import re
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional, Union
import pandas as pd
from firewatch.data.schemas import ObservationNormalized, ValidationReport, ValidationIssue


# Column aliases to support varied FIRMS formats and regional exports
COLUMN_ALIASES = {
    "lat": "latitude",
    "long": "longitude",
    "lon": "longitude",
    "date": "acq_date",
    "time": "acq_time",
    "bright_ti4": "bright_ti4",
    "bright_ti5": "bright_ti5",
    "brightness": "brightness",
    "bright_t31": "bright_t31"
}


def compute_observation_id(lat: float, lon: float, acq_date: str, acq_time: str, satellite: str, instrument: str) -> str:
    """Generate a deterministic SHA-256 hash ID for an observation."""
    raw_str = f"{lat:.5f}_{lon:.5f}_{acq_date}_{acq_time}_{satellite.lower()}_{instrument.lower()}"
    return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()[:16]


def parse_confidence(val: Any) -> Tuple[float, str, Optional[str]]:
    """
    Parse and normalize confidence value.
    Returns: (normalized_confidence [0.0, 1.0], category ('low'|'nominal'|'high'), raw_str)
    """
    if pd.isna(val) or val is None or str(val).strip() == "":
        return 0.50, "nominal", "missing"
    
    val_str = str(val).strip().lower()
    
    # Check categorical strings (VIIRS format)
    if val_str in ("low", "l"):
        return 0.30, "low", str(val)
    elif val_str in ("nominal", "n"):
        return 0.65, "nominal", str(val)
    elif val_str in ("high", "h"):
        return 0.95, "high", str(val)
    
    # Try numeric parsing (MODIS format: 0 to 100)
    try:
        num = float(val)
        if 0.0 <= num <= 100.0:
            norm = round(num / 100.0, 4)
            if num >= 80.0:
                cat = "high"
            elif num >= 30.0:
                cat = "nominal"
            else:
                cat = "low"
            return norm, cat, str(val)
        elif 0.0 <= num <= 1.0:
            # Already normalized 0-1
            norm = round(num, 4)
            cat = "high" if norm >= 0.8 else ("nominal" if norm >= 0.3 else "low")
            return norm, cat, str(val)
        else:
            return 0.50, "nominal", f"out_of_bounds({val})"
    except ValueError:
        return 0.50, "nominal", f"unrecognized({val})"


def parse_acq_datetime(date_str: str, time_str: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse and validate date and time into standard ISO 8601 UTC.
    acq_date is expected as YYYY-MM-DD or YYYY/MM/DD.
    acq_time is expected as HHMM (e.g. '0048', '907', '1430') or HH:MM.
    Strictly validates month (1-12), day (1-31), hour (0-23), minute (0-59).
    """
    date_clean = str(date_str).strip().replace("/", "-")
    
    # Clean time string to 4 digits HHMM
    t_clean = str(time_str).strip().replace(":", "")
    if len(t_clean) < 4:
        t_clean = t_clean.zfill(4)
    if len(t_clean) > 4:
        t_clean = t_clean[:4]
    
    if not (t_clean.isdigit() and len(t_clean) == 4):
        return None, f"Invalid time format: '{time_str}', expected HHMM"

    try:
        dt = datetime.strptime(f"{date_clean} {t_clean}", "%Y-%m-%d %H%M")
    except ValueError as ve:
        return None, f"Invalid date or time calendar values: {ve}"
    
    year = dt.year
    if year < 2000 or year > 2035:
        return None, f"Date year out of expected operational satellite range: {year}"
    
    iso_dt = dt.strftime("%Y-%m-%dT%H:%M:00Z")
    return iso_dt, None


class CSVValidator:
    """Validates and parses NASA FIRMS active fire CSV files."""

    REQUIRED_FIELDS = ["latitude", "longitude", "acq_date", "acq_time"]

    @classmethod
    def validate_csv(
        cls,
        csv_source: Union[str, io.StringIO, io.BytesIO],
        dataset_name: str = "FIRMS_Dataset",
        max_rows: Optional[int] = None
    ) -> Tuple[List[ObservationNormalized], ValidationReport]:
        """
        Ingest, validate, and normalize FIRMS CSV records.
        Does not silently drop bad rows; records full validation audit.
        """
        report = ValidationReport(
            dataset_name=dataset_name,
            source_product="NASA_FIRMS_GENERIC"
        )
        
        try:
            if isinstance(csv_source, io.BytesIO):
                df = pd.read_csv(csv_source, nrows=max_rows, dtype=str)
            elif isinstance(csv_source, str) and "\n" in csv_source:
                df = pd.read_csv(io.StringIO(csv_source), nrows=max_rows, dtype=str)
            else:
                df = pd.read_csv(csv_source, nrows=max_rows, dtype=str)
        except Exception as e:
            report.total_rows = 0
            report.invalid_rows = 1
            report.rejection_reasons.append(
                ValidationIssue(row_number=0, reason=f"Failed to read CSV: {str(e)}")
            )
            return [], report

        report.total_rows = len(df)
        if df.empty:
            report.rejection_reasons.append(
                ValidationIssue(row_number=0, reason="CSV file is empty")
            )
            return [], report

        # Standardize column headers (lowercase, trimmed)
        original_cols = list(df.columns)
        col_map = {}
        for c in original_cols:
            clean_c = c.strip().lower()
            mapped = COLUMN_ALIASES.get(clean_c, clean_c)
            col_map[c] = mapped
        
        df_renamed = df.rename(columns=col_map)
        
        # Check required columns
        missing_required = [req for req in cls.REQUIRED_FIELDS if req not in df_renamed.columns]
        if missing_required:
            report.invalid_rows = report.total_rows
            report.rejection_reasons.append(
                ValidationIssue(
                    row_number=0,
                    reason=f"Missing required columns: {missing_required}. Present columns: {list(df_renamed.columns)}"
                )
            )
            return [], report

        # Detect source product type
        if "bright_ti4" in df_renamed.columns:
            report.source_product = "VIIRS_NRT"
            default_instrument = "VIIRS"
        elif "bright_t31" in df_renamed.columns or "brightness" in df_renamed.columns:
            report.source_product = "MODIS_C6_1_NRT"
            default_instrument = "MODIS"
        else:
            report.source_product = "FIRMS_CSV_GENERIC"
            default_instrument = "SatelliteSensor"

        # Track missing values across columns
        for col in df_renamed.columns:
            missing_count = int(df_renamed[col].isna().sum() + (df_renamed[col].str.strip() == "").sum())
            if missing_count > 0:
                report.missing_field_counts[col] = missing_count

        valid_records: List[ObservationNormalized] = []
        seen_hashes = set()
        dates_seen = []

        for idx, row in df_renamed.iterrows():
            row_num = idx + 1
            raw_dict = row.to_dict()

            # 1. Validate Coordinates
            lat_raw = row.get("latitude")
            lon_raw = row.get("longitude")
            
            try:
                lat = float(lat_raw)
                lon = float(lon_raw)
            except (ValueError, TypeError):
                report.invalid_rows += 1
                report.rejection_reasons.append(
                    ValidationIssue(
                        row_number=row_num,
                        reason=f"Non-numeric coordinates: lat='{lat_raw}', lon='{lon_raw}'",
                        raw_snippet=raw_dict
                    )
                )
                continue

            if not (-90.0 <= lat <= 90.0):
                report.invalid_rows += 1
                report.rejection_reasons.append(
                    ValidationIssue(
                        row_number=row_num,
                        reason=f"Latitude out of bounds [-90, 90]: {lat}",
                        field="latitude",
                        raw_snippet=raw_dict
                    )
                )
                continue

            if not (-180.0 <= lon <= 180.0):
                report.invalid_rows += 1
                report.rejection_reasons.append(
                    ValidationIssue(
                        row_number=row_num,
                        reason=f"Longitude out of bounds [-180, 180]: {lon}",
                        field="longitude",
                        raw_snippet=raw_dict
                    )
                )
                continue

            # 2. Validate Acquisition Date and Time
            acq_date_val = str(row.get("acq_date", "")).strip()
            acq_time_val = str(row.get("acq_time", "")).strip()
            
            iso_dt, time_err = parse_acq_datetime(acq_date_val, acq_time_val)
            if time_err or iso_dt is None:
                report.invalid_rows += 1
                report.rejection_reasons.append(
                    ValidationIssue(
                        row_number=row_num,
                        reason=time_err or "Invalid date/time",
                        field="acq_date/acq_time",
                        raw_snippet=raw_dict
                    )
                )
                continue

            # 3. Satellite and Instrument detection
            satellite = str(row.get("satellite", "")).strip()
            if not satellite or satellite.lower() == "nan":
                # Standard NASA naming fallbacks
                if "t" == satellite.lower() or "terra" in report.source_product.lower():
                    satellite = "Terra"
                elif "a" == satellite.lower() or "aqua" in report.source_product.lower():
                    satellite = "Aqua"
                elif "n" == satellite.lower():
                    satellite = "Suomi-NPP"
                else:
                    satellite = "Unknown Satellite"
            else:
                if satellite.upper() == "T":
                    satellite = "Terra"
                elif satellite.upper() == "A":
                    satellite = "Aqua"
                elif satellite.upper() == "N":
                    satellite = "Suomi-NPP"
                elif satellite.upper() == "1":
                    satellite = "NOAA-20"
                elif satellite.upper() == "2":
                    satellite = "NOAA-21"

            instrument = str(row.get("instrument", "")).strip()
            if not instrument or instrument.lower() == "nan":
                instrument = default_instrument

            # 4. Check Duplicates
            obs_id = compute_observation_id(lat, lon, acq_date_val, acq_time_val, satellite, instrument)
            if obs_id in seen_hashes:
                report.duplicate_rows += 1
                report.invalid_rows += 1
                report.rejection_reasons.append(
                    ValidationIssue(
                        row_number=row_num,
                        reason=f"Duplicate observation detected (ID: {obs_id})",
                        field="duplicate",
                        raw_snippet=raw_dict
                    )
                )
                continue
            seen_hashes.add(obs_id)

            # 5. Parse Confidence
            conf_norm, conf_cat, conf_raw = parse_confidence(row.get("confidence"))

            # 6. Parse FRP (Fire Radiative Power)
            frp_val: Optional[float] = None
            frp_raw = row.get("frp")
            if pd.notna(frp_raw) and str(frp_raw).strip() != "":
                try:
                    frp_float = float(frp_raw)
                    if frp_float >= 0.0:
                        frp_val = round(frp_float, 2)
                    else:
                        report.invalid_rows += 1
                        report.rejection_reasons.append(
                            ValidationIssue(
                                row_number=row_num,
                                reason=f"Negative FRP value: {frp_float}",
                                field="frp",
                                raw_snippet=raw_dict
                            )
                        )
                        continue
                except (ValueError, TypeError):
                    frp_val = None

            # 7. Parse Brightness Temperature
            brightness_val: Optional[float] = None
            for b_col in ["bright_ti4", "brightness"]:
                if b_col in row and pd.notna(row[b_col]) and str(row[b_col]).strip() != "":
                    try:
                        b_float = float(row[b_col])
                        if b_float > 0.0:
                            brightness_val = round(b_float, 2)
                            break
                        else:
                            report.invalid_rows += 1
                            report.rejection_reasons.append(
                                ValidationIssue(
                                    row_number=row_num,
                                    reason=f"Non-positive brightness temperature: {b_float}",
                                    field=b_col,
                                    raw_snippet=raw_dict
                                )
                            )
                            continue
                    except ValueError:
                        pass

            bright_sec: Optional[float] = None
            for s_col in ["bright_ti5", "bright_t31"]:
                if s_col in row and pd.notna(row[s_col]) and str(row[s_col]).strip() != "":
                    try:
                        s_float = float(row[s_col])
                        if s_float > 0.0:
                            bright_sec = round(s_float, 2)
                            break
                    except ValueError:
                        pass

            # 8. Scan & Track
            scan_val: Optional[float] = None
            track_val: Optional[float] = None
            try:
                if pd.notna(row.get("scan")):
                    scan_val = float(row["scan"])
                if pd.notna(row.get("track")):
                    track_val = float(row["track"])
            except ValueError:
                pass

            daynight = str(row.get("daynight", "")).strip().upper()
            if daynight not in ("D", "N"):
                daynight = None

            dates_seen.append(acq_date_val)

            obs = ObservationNormalized(
                id=obs_id,
                latitude=round(lat, 5),
                longitude=round(lon, 5),
                acq_date=acq_date_val,
                acq_time=acq_time_val,
                acq_datetime=iso_dt,
                satellite=satellite,
                instrument=instrument,
                confidence_raw=conf_raw,
                confidence_normalized=conf_norm,
                confidence_category=conf_cat,
                brightness_kelvin=brightness_val,
                bright_secondary=bright_sec,
                frp=frp_val,
                daynight=daynight,
                scan=scan_val,
                track=track_val,
                source_product=report.source_product,
                raw_data=raw_dict
            )
            valid_records.append(obs)

        report.valid_rows = len(valid_records)
        if dates_seen:
            report.acq_date_min = min(dates_seen)
            report.acq_date_max = max(dates_seen)

        return valid_records, report
