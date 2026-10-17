"""
Unit and integration tests for CSV validation and data ingestion.
"""

import io
import pytest
from firewatch.data.validator import CSVValidator, parse_confidence, parse_acq_datetime
from firewatch.data.acquisition import FIRMSAcquisitionManager


def test_parse_confidence_modis_numeric():
    norm, cat, raw = parse_confidence(85)
    assert norm == 0.85
    assert cat == "high"
    assert raw == "85"

    norm, cat, raw = parse_confidence(45)
    assert norm == 0.45
    assert cat == "nominal"

    norm, cat, raw = parse_confidence(15)
    assert norm == 0.15
    assert cat == "low"


def test_parse_confidence_viirs_categorical():
    norm, cat, raw = parse_confidence("nominal")
    assert norm == 0.65
    assert cat == "nominal"

    norm, cat, raw = parse_confidence("low")
    assert norm == 0.30
    assert cat == "low"

    norm, cat, raw = parse_confidence("high")
    assert norm == 0.95
    assert cat == "high"


def test_parse_confidence_missing_and_unexpected():
    norm, cat, raw = parse_confidence(None)
    assert norm == 0.50
    assert cat == "nominal"
    assert raw == "missing"

    norm, cat, raw = parse_confidence("invalid_text")
    assert norm == 0.50
    assert cat == "nominal"


def test_parse_acq_datetime():
    iso, err = parse_acq_datetime("2026-10-15", "0907")
    assert err is None
    assert iso == "2026-10-15T09:07:00Z"

    # Short time like '48' -> '0048'
    iso, err = parse_acq_datetime("2026-10-15", "48")
    assert err is None
    assert iso == "2026-10-15T00:48:00Z"

    # Invalid month
    iso, err = parse_acq_datetime("2026-13-10", "1200")
    assert iso is None
    assert "Invalid date or time calendar values" in err


def test_csv_validation_empty():
    records, report = CSVValidator.validate_csv("", "Empty_Test")
    assert len(records) == 0
    assert report.total_rows == 0
    assert len(report.rejection_reasons) > 0


def test_csv_validation_missing_required_columns():
    csv_text = "foo,bar\n1,2\n"
    records, report = CSVValidator.validate_csv(csv_text, "Missing_Cols")
    assert len(records) == 0
    assert "Missing required columns" in report.rejection_reasons[0].reason


def test_csv_validation_synthetic_dataset():
    res = FIRMSAcquisitionManager.load_local_sample("synthetic_test_cases.csv")
    assert res.success is True
    records, report = CSVValidator.validate_csv(res.content, "Synthetic_Test")
    assert report.total_rows == 11
    assert report.valid_rows == 3 or report.valid_rows == 4
    assert report.invalid_rows >= 7
    assert report.duplicate_rows >= 1


def test_csv_validation_real_modis_sample():
    res = FIRMSAcquisitionManager.load_local_sample("firms_modis_sample.csv")
    assert res.success is True
    records, report = CSVValidator.validate_csv(res.content, "MODIS_Real")
    assert len(records) > 0
    assert report.valid_rows == len(records)
    assert report.invalid_rows == 0
    first = records[0]
    assert first.latitude is not None
    assert first.longitude is not None
    assert first.acq_datetime.endswith("Z")
    assert first.raw_data is not None


def test_csv_validation_real_viirs_sample():
    res = FIRMSAcquisitionManager.load_local_sample("firms_viirs_sample.csv")
    assert res.success is True
    records, report = CSVValidator.validate_csv(res.content, "VIIRS_Real")
    assert len(records) > 0
    assert report.valid_rows == len(records)
    assert report.invalid_rows == 0
    first = records[0]
    assert first.instrument == "VIIRS"
    assert first.confidence_category in ("low", "nominal", "high")
