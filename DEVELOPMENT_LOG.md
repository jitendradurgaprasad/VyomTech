# FireWatch AI - Development Log

## Project Summary
- **System**: FireWatch AI - Satellite-Based Active Fire Observation Triage Dashboard
- **Repository**: `https://github.com/jitendradurgaprasad/VyomTech.git`
- **Primary Input**: NASA FIRMS Active Fire CSV data (MODIS C6.1, VIIRS Suomi-NPP C2, VIIRS NOAA-20/21)
- **Nature of System**: Observation triage and decision-support system. NOT a confirmed wildfire detector or emergency dispatch tool.

---

## Phase 1: Repository Inspection, Architecture Setup & Environment Verification
- **Status**: Completed
- **Commit Hash**: `ece14286574054107c64a9b5d60db1e6164a3ce3` (Phase 1)
- **Final Verified Remote Commit Hash**: `f1bad0c36c742098496ef129e6b59d9572ed05b3` (Phases 2-10)
- **Actions**:
  - Inspected repository and environment. Verified Python 3.11.3, pip 26.2.1.
  - Installed missing geospatial packages `folium` (0.20.0) and `streamlit-folium` (0.27.4).
  - Initialized git repository with `main` branch.
  - Configured remote origin: `https://github.com/jitendradurgaprasad/VyomTech.git`.
  - Added comprehensive `.gitignore` preventing secrets, databases, large archives, and logs from being committed.
  - Created `.env.example` with documented configurations and simulation defaults.
  - Created `requirements.txt`.

---

## Phase 2: NASA FIRMS Data Acquisition, CSV Ingestion & Strict Validation
- **Status**: Completed
- **Actions**:
  - Implemented `firewatch/data/schemas.py` using Pydantic models for `ObservationNormalized` and `ValidationReport`.
  - Implemented `firewatch/data/validator.py`:
    - Strict validation of required fields (`latitude`, `longitude`, `acq_date`, `acq_time`).
    - Validates latitude in `[-90, 90]`, longitude in `[-180, 180]`.
    - Robust date and time validation (`datetime.strptime`), rejecting out-of-range calendar dates and times.
    - Non-negative FRP validation and positive brightness temperature validation.
    - Confidence normalizer handling both MODIS (0–100% numeric) and VIIRS (`low`, `nominal`, `high` categorical) formats.
    - Duplicate detection using deterministic SHA-256 hash calculation.
    - Generates downloadable `ValidationReport` tracking row-by-row rejection reasons, missing-field frequencies, and acceptance rates.
  - Implemented `firewatch/data/acquisition.py`:
    - Direct downloader for live NASA FIRMS 24h NRT CSV feeds (South Asia and Global feeds for MODIS and VIIRS).
    - API client for FIRMS REST API using `FIRMS_MAP_KEY`.
    - Local benchmark sample loader.
  - Acquired and saved genuine benchmark samples:
    - `data/sample/firms_modis_sample.csv` (136 real MODIS observations).
    - `data/sample/firms_viirs_sample.csv` (300 real VIIRS observations).
    - `data/sample/synthetic_test_cases.csv` (11 clearly labelled synthetic records covering all edge cases, out-of-bounds coords, duplicates, and malformed inputs).
  - Built `tests/test_validator.py` with 9 passing tests.

---

## Phase 3: Explainable Priority Scoring & Spatial Clustering
- **Status**: Completed
- **Actions**:
  - Implemented `firewatch/analysis/clustering.py`:
    - Spatial clustering using Scikit-Learn `DBSCAN` with Haversine distance on radian coordinates.
    - Configurable `eps_km` (default 10.0 km) and `min_samples` (default 2).
    - Preserves individual observation records while augmenting with `cluster_id`, `cluster_size`, and `repeat_detection_count`.
    - Cluster summary metrics generator (centroids, observation counts, FRP distributions).
  - Implemented `firewatch/analysis/priority.py`:
    - Multi-factor deterministic explainable priority scoring formula:
      - Confidence score ($S_{\text{conf}}$)
      - FRP saturation score ($S_{\text{frp}} = 1 - e^{-\text{FRP} / \text{ref\_FRP}}$), with neutral benchmark (0.35) for missing FRP
      - Temporal recency decay ($S_{\text{rec}} = e^{-\Delta t / \text{window}}$)
      - Spatial cluster size score ($S_{\text{cluster}}$)
      - Repeat detection corroboration ($S_{\text{repeat}}$)
    - Transparent score breakdown: attaches plain-English reasons and explicit sensor uncertainty limitations to every record.
    - Categorization: "High Review Priority" ($\ge 0.70$), "Medium Review Priority" ($\ge 0.40$), and "Low Review Priority" ($< 0.40$).
  - Built `tests/test_priority.py` (4 tests) and `tests/test_clustering.py` (3 tests). All passing.

---

## Phase 4: Geographical Context, Mapping & Location Analysis
- **Status**: Completed
- **Actions**:
  - Implemented `firewatch/analysis/context.py`:
    - Geographic bounding box resolution for administrative jurisdictions.
    - Non-fabrication guarantee: Any location outside verified administrative bounds is strictly assigned `Jurisdiction unknown` and routed to the central review desk.
  - Implemented `firewatch/ui/map_view.py`:
    - Interactive Folium map with OpenStreetMap and Esri Satellite basemap tile layers.
    - Circle markers colored by triage priority (Red: High, Orange: Medium, Blue: Low).
    - Rich interactive popups displaying coordinates, timestamps, satellite platform, confidence, FRP, cluster metrics, region, jurisdiction, triage reasons, and uncertainty disclaimers.
    - Toggleable MarkerCluster and individual detection layers.
  - Implemented `firewatch/ui/charts.py`:
    - Plotly charts for priority level distributions, FRP histograms, satellite platform shares, and Confidence vs FRP scatter analysis.
  - Built `tests/test_context.py` (3 tests). All passing.

---

## Phase 5: Persistent Feedback Workflow & Audit Trail
- **Status**: Completed
- **Actions**:
  - Implemented `firewatch/storage/database.py`:
    - SQLite persistence manager with WAL mode and foreign key constraints.
    - Tables: `observations`, `reviews`, `authorities`, `notification_audit`.
    - Preserves full audit history: When an analyst submits a corrected assessment, a new review row is created with `is_correction = 1`, preserving the historical record.
    - Original FIRMS satellite observation attributes are never overwritten or altered.
  - Built `tests/test_feedback.py` (1 test). Passing.

---

## Phase 6 & 7: Authority Directory, Notification Centre & Provider Abstraction
- **Status**: Completed
- **Actions**:
  - Implemented `firewatch/notifications/providers.py`:
    - Base provider abstract interface.
    - `SimulationNotificationProvider`: Default provider. Formats standard alert payload, records simulation delivery, and never contacts external networks.
    - `SmtpNotificationProvider`: For authorized SMTP email delivery (active only when simulation mode is explicitly disabled). Implements credential masking.
    - `WebhookNotificationProvider`: For authorized HTTP webhook dispatch.
  - Implemented `firewatch/notifications/manager.py`:
    - Location-aware routing matching observation jurisdiction to authority directory (with fallback to Central Review Queue).
    - Standardized review notice generation containing alert ID, coordinates, OpenStreetMap link, telemetry, priority breakdown, prominent UNVERIFIED detection disclaimer, and recommended human verification actions.
    - Duplicate notification protection with 60-minute cooldown throttling.
    - Chronological audit logging in SQLite tracking status (`simulated`, `provider_accepted`, `delivered`, `failed`).
  - Implemented `tests/test_notifications.py` (4 tests) and `tests/test_privacy_security.py` (2 tests). All passing.

---

## Phase 8: Exports, Audit Logs & Evaluation Views
- **Status**: Completed
- **Actions**:
  - Integrated comprehensive CSV export capabilities:
    - Filtered observations CSV export.
    - Full review feedback history CSV export.
    - Notification audit logs CSV export.
    - Validation report JSON & CSV export.
  - Integrated in-app evaluation view with one-click Pytest runner and verification coverage matrix.

---

## Phase 9: Quality Assurance, Security Inspection & Reliability Verification
- **Status**: Completed
- **Actions**:
  - Executed full Pytest suite across all test modules: 26 passed out of 26 tests in 9.49 seconds.
  - Verified security: `.env` and `.db` files ignored by `.gitignore`.
  - Verified password masking in notification error logs.
  - Verified non-fabrication in synthetic test suite and unknown jurisdiction fallbacks.

---

## Phase 10: Streamlit Dashboard Assembly & Documentation
- **Status**: Completed
- **Actions**:
  - Built `app.py` Streamlit entrypoint with responsive 11-view navigation:
    1. System Overview
    2. Data Ingestion & Import
    3. Interactive Map & Table
    4. Priority Review Queue
    5. Observation Details & Review
    6. Global Feedback History
    7. Authority Directory
    8. Notification Centre
    9. Data Validation Report
    10. Evaluation & Testing
    11. Settings & About
  - Built comprehensive `README.md` with system architecture diagrams, formula breakdowns, installation steps, and troubleshooting.
  - Added `LICENSE` (MIT).
