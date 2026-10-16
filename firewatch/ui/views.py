"""
Modular Streamlit Dashboard Views for FireWatch AI.
"""

from __future__ import annotations
import os
import io
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from firewatch.config import AppSettings, ScoringConfig, ClusteringConfig
from firewatch.data.schemas import ObservationNormalized, ValidationReport
from firewatch.data.validator import CSVValidator
from firewatch.data.acquisition import FIRMSAcquisitionManager
from firewatch.analysis.priority import PriorityRanker
from firewatch.analysis.clustering import SpatialClusterer
from firewatch.analysis.context import GeoContextResolver
from firewatch.storage.database import DatabaseManager
from firewatch.notifications.manager import NotificationManager
from firewatch.ui.map_view import build_folium_map
from firewatch.ui.charts import (
    create_priority_distribution_chart,
    create_frp_histogram,
    create_satellite_share_pie,
    create_confidence_vs_frp_scatter
)


def observations_to_df(observations: List[ObservationNormalized]) -> pd.DataFrame:
    """Convert observation objects to a presentation DataFrame."""
    if not observations:
        return pd.DataFrame()
    rows = []
    for o in observations:
        rows.append({
            "ID": o.id,
            "Priority Score": o.priority_score,
            "Priority Level": o.priority_level,
            "Confidence (%)": round(o.confidence_normalized * 100, 1),
            "FRP (MW)": o.frp,
            "Latitude": o.latitude,
            "Longitude": o.longitude,
            "Acquisition Time": o.acq_datetime,
            "Satellite": o.satellite,
            "Instrument": o.instrument,
            "Cluster Size": o.cluster_size,
            "Repeat Detections": o.repeat_detection_count,
            "Region": o.administrative_region,
            "Jurisdiction": o.jurisdiction
        })
    return pd.DataFrame(rows)


# ==============================================================================
# VIEW 1: OVERVIEW
# ==============================================================================
def render_overview(observations: List[ObservationNormalized], db: DatabaseManager, settings: AppSettings):
    st.subheader("System Overview & Operational Metrics")
    
    st.warning(
        f"**Mandatory Operating Notice**: {settings.disclaimer}",
        icon="ℹ️"
    )

    # Calculate live KPIs
    total_imported = len(observations)
    high_priority = sum(1 for o in observations if o.priority_level == "High Review Priority")
    medium_priority = sum(1 for o in observations if o.priority_level == "Medium Review Priority")
    low_priority = sum(1 for o in observations if o.priority_level == "Low Review Priority")
    
    reviews = db.get_all_reviews()
    reviewed_ids = set(r["observation_id"] for r in reviews)
    awaiting_review = sum(1 for o in observations if o.id not in reviewed_ids)
    
    notif_logs = db.get_notification_logs(limit=500)
    simulated_notifs = sum(1 for n in notif_logs if n.get("status") == "simulated")

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Observations", total_imported)
    col2.metric("High Review Priority", high_priority, delta=f"{high_priority} urgent", delta_color="inverse")
    col3.metric("Awaiting Human Review", awaiting_review)
    col4.metric("Reviews Logged", len(reviews))
    col5.metric("Simulated Alerts", simulated_notifs)

    st.markdown("---")

    # Analytics charts
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(create_priority_distribution_chart(observations), use_container_width=True)
    with c2:
        st.plotly_chart(create_satellite_share_pie(observations), use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        st.plotly_chart(create_frp_histogram(observations), use_container_width=True)
    with c4:
        st.plotly_chart(create_confidence_vs_frp_scatter(observations), use_container_width=True)


# ==============================================================================
# VIEW 2: DATA INGESTION & IMPORT
# ==============================================================================
def render_data_ingestion(db: DatabaseManager, settings: AppSettings) -> Optional[List[ObservationNormalized]]:
    st.subheader("NASA FIRMS Data Acquisition & CSV Ingestion")

    st.info(
        "Ingest genuine NASA FIRMS active fire datasets or custom CSV files. "
        "Original source attributes are strictly preserved and validated."
    )

    source_tab1, source_tab2, source_tab3 = st.tabs([
        "Built-in Genuine Samples", "Live FIRMS Download / API", "Upload Custom CSV"
    ])

    new_observations = None
    validation_rep = None

    with source_tab1:
        st.markdown("#### Load Verified Benchmark Datasets")
        st.caption("Pre-loaded genuine NASA FIRMS NRT CSV files and labelled synthetic test suite.")
        
        col_b1, col_b2, col_b3 = st.columns(3)
        with col_b1:
            if st.button("Load MODIS South Asia Sample (Genuine)", use_container_width=True):
                with st.spinner("Loading and validating MODIS sample..."):
                    res = FIRMSAcquisitionManager.load_local_sample("firms_modis_sample.csv")
                    if res.success:
                        obs, rep = CSVValidator.validate_csv(res.content, "MODIS_South_Asia_24h")
                        new_observations, validation_rep = obs, rep
                        st.session_state["validation_report"] = rep
                        st.success(f"Loaded {rep.valid_rows} valid records from MODIS sample.")
                    else:
                        st.error(res.error)

        with col_b2:
            if st.button("Load VIIRS South Asia Sample (Genuine)", use_container_width=True):
                with st.spinner("Loading and validating VIIRS sample..."):
                    res = FIRMSAcquisitionManager.load_local_sample("firms_viirs_sample.csv")
                    if res.success:
                        obs, rep = CSVValidator.validate_csv(res.content, "VIIRS_South_Asia_24h")
                        new_observations, validation_rep = obs, rep
                        st.session_state["validation_report"] = rep
                        st.success(f"Loaded {rep.valid_rows} valid records from VIIRS sample.")
                    else:
                        st.error(res.error)

        with col_b3:
            if st.button("Load Synthetic Test Suite (Edge Cases)", use_container_width=True):
                with st.spinner("Loading and validating synthetic test cases..."):
                    res = FIRMSAcquisitionManager.load_local_sample("synthetic_test_cases.csv")
                    if res.success:
                        obs, rep = CSVValidator.validate_csv(res.content, "Synthetic_Test_Cases")
                        new_observations, validation_rep = obs, rep
                        st.session_state["validation_report"] = rep
                        st.warning(f"Ingested SYNTHETIC test file. Valid: {rep.valid_rows}, Rejected: {rep.invalid_rows}")
                    else:
                        st.error(res.error)

    with source_tab2:
        st.markdown("#### Live NASA FIRMS Download")
        feed_choice = st.selectbox(
            "Select Live NRT CSV Feed:",
            [
                ("modis_south_asia_24h", "NASA MODIS C6.1 South Asia (Past 24 Hours)"),
                ("viirs_south_asia_24h", "NASA Suomi-NPP VIIRS South Asia (Past 24 Hours)"),
                ("modis_global_24h", "NASA MODIS C6.1 Global (Past 24 Hours)"),
                ("viirs_global_24h", "NASA Suomi-NPP VIIRS Global (Past 24 Hours)")
            ],
            format_func=lambda x: x[1]
        )

        col_live1, col_live2 = st.columns([1, 2])
        with col_live1:
            if st.button("Fetch Live Satellite Feed", type="primary"):
                with st.spinner(f"Connecting to NASA FIRMS ({feed_choice[0]})..."):
                    res = FIRMSAcquisitionManager.fetch_live_feed(feed_choice[0])
                    if res.success:
                        obs, rep = CSVValidator.validate_csv(res.content, feed_choice[0])
                        new_observations, validation_rep = obs, rep
                        st.session_state["validation_report"] = rep
                        st.success(f"Live download successful! Valid records: {rep.valid_rows}, Invalid: {rep.invalid_rows}")
                    else:
                        st.error(f"Live fetch failed: {res.error}")
        with col_live2:
            st.caption(
                "Directly streams genuine near-real-time thermal anomaly CSV feeds published by NASA LANCE ESDIS. "
                "No API key required for public 24h feeds."
            )

    with source_tab3:
        st.markdown("#### Upload Custom FIRMS CSV")
        uploaded_file = st.file_uploader("Upload FIRMS CSV (MODIS or VIIRS format)", type=["csv"])
        if uploaded_file is not None:
            if st.button("Validate and Process Uploaded CSV"):
                content = uploaded_file.getvalue().decode("utf-8", errors="replace")
                obs, rep = CSVValidator.validate_csv(content, uploaded_file.name)
                new_observations, validation_rep = obs, rep
                st.session_state["validation_report"] = rep
                st.success(f"Processed '{uploaded_file.name}': {rep.valid_rows} valid records, {rep.invalid_rows} rejected.")

    if new_observations is not None:
        # Run spatial clustering, context resolution, and explainable ranking
        with st.spinner("Computing spatial clusters, geographic jurisdictions, and explainable priority scores..."):
            clusterer = SpatialClusterer(settings.clustering)
            clusterer.cluster_observations(new_observations)

            GeoContextResolver.enrich_observations(new_observations)

            ranker = PriorityRanker(settings.scoring)
            ranked_obs = ranker.rank_observations(new_observations)

            db.save_observations(ranked_obs)
            st.session_state["observations"] = ranked_obs
            st.rerun()

    return None


# ==============================================================================
# VIEW 3: INTERACTIVE MAP & FILTERABLE TABLE
# ==============================================================================
def render_interactive_map(observations: List[ObservationNormalized], db: DatabaseManager):
    st.subheader("Geographical Map & Filterable Observation Table")

    if not observations:
        st.info("No active observations in memory. Please ingest or load a dataset first.")
        return

    # Filter controls
    with st.expander("Filter and Display Controls", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            priority_filter = st.multiselect(
                "Filter Priority Level:",
                ["High Review Priority", "Medium Review Priority", "Low Review Priority"],
                default=["High Review Priority", "Medium Review Priority", "Low Review Priority"]
            )
        with c2:
            satellites = sorted(list(set(o.satellite for o in observations)))
            satellite_filter = st.multiselect("Filter Satellite Platform:", satellites, default=satellites)
        with c3:
            min_frp = st.number_input("Minimum FRP (MW):", min_value=0.0, value=0.0, step=5.0)
        with c4:
            cluster_only = st.checkbox("Only Show Multi-point Clusters", value=False)

    # Filter observations
    filtered = [
        o for o in observations
        if (o.priority_level in priority_filter) and
           (o.satellite in satellite_filter) and
           ((o.frp or 0.0) >= min_frp) and
           (not cluster_only or (o.cluster_size or 1) > 1)
    ]

    st.write(f"Showing **{len(filtered)}** of {len(observations)} total observations.")

    selected_id = st.session_state.get("selected_obs_id", None)

    # Render Folium Map
    folium_map = build_folium_map(filtered, selected_id=selected_id)
    st_folium(folium_map, width=None, height=520, returned_objects=[])

    st.markdown("---")
    st.markdown("#### Filtered Observations Data Table")

    df_display = observations_to_df(filtered)
    if not df_display.empty:
        st.dataframe(df_display, use_container_width=True, height=280)

        # Export CSV button
        csv_buffer = io.StringIO()
        df_display.to_csv(csv_buffer, index=False)
        st.download_button(
            label="Download Filtered Observations (CSV)",
            data=csv_buffer.getvalue(),
            file_name=f"firewatch_filtered_observations_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )


# ==============================================================================
# VIEW 4: PRIORITY REVIEW QUEUE
# ==============================================================================
def render_priority_queue(observations: List[ObservationNormalized], db: DatabaseManager, notif_manager: NotificationManager):
    st.subheader("Priority Review Queue (Explainable Ranking)")

    if not observations:
        st.info("No active observations in queue. Ingest a dataset to populate the triage queue.")
        return

    reviews = db.get_latest_review_map()
    pending = [o for o in observations if o.id not in reviews]
    reviewed = [o for o in observations if o.id in reviews]

    st.write(
        f"Queue contains **{len(pending)}** unreviewed detections and **{len(reviewed)}** completed reviews."
    )

    top_obs = pending[:50] if pending else observations[:50]

    for obs in top_obs:
        with st.container():
            is_high = obs.priority_level == "High Review Priority"
            card_title = f"{'🔴' if is_high else '🟡'} [{obs.priority_level}] Observation: {obs.id} (Score: {obs.priority_score:.4f})"
            
            with st.expander(card_title, expanded=is_high):
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.markdown(f"**Coordinates:** `{obs.latitude:.5f}, {obs.longitude:.5f}` | **Region:** {obs.administrative_region} | **Jurisdiction:** {obs.jurisdiction}")
                    st.markdown(f"**Acquisition:** {obs.acq_datetime} | **Platform:** {obs.satellite} ({obs.instrument})")
                    st.markdown(f"**Confidence:** {obs.confidence_category.upper()} ({obs.confidence_normalized*100:.1f}%) | **FRP:** {f'{obs.frp:.1f} MW' if obs.frp is not None else 'N/A'}")
                    
                    st.markdown("##### Score Explanations:")
                    for r in (obs.priority_reasons or []):
                        st.markdown(f"- {r}")

                    st.markdown("##### Limitations & Sensor Uncertainty:")
                    for l in (obs.priority_limitations or []):
                        st.markdown(f"- *{l}*")

                with c2:
                    st.markdown("##### Human Triage Action")
                    if st.button(f"Inspect & Review", key=f"btn_review_{obs.id}"):
                        st.session_state["selected_obs_id"] = obs.id
                        st.session_state["nav_selection"] = "Observation Details & Review"
                        st.rerun()

                    if st.button(f"Simulate Authority Alert", key=f"btn_notif_{obs.id}"):
                        res = notif_manager.process_notification(obs, trigger_reason="Manual triage escalation")
                        if res.success:
                            st.success(f"Simulated alert dispatched: {res.provider_response}")
                        else:
                            st.error(f"Dispatch blocked or failed: {res.provider_response}")


# ==============================================================================
# VIEW 5: OBSERVATION DETAILS & HUMAN REVIEW
# ==============================================================================
def render_observation_details(observations: List[ObservationNormalized], db: DatabaseManager):
    st.subheader("Observation Deep Dive & Feedback Submission")

    if not observations:
        st.info("No observations available.")
        return

    obs_ids = [o.id for o in observations]
    current_sel = st.session_state.get("selected_obs_id", obs_ids[0])
    idx = obs_ids.index(current_sel) if current_sel in obs_ids else 0

    selected_id = st.selectbox("Select Observation by ID:", obs_ids, index=idx)
    st.session_state["selected_obs_id"] = selected_id
    obs = next((o for o in observations if o.id == selected_id), None)
    if not obs:
        st.error("Observation not found.")
        return

    # Details Layout
    col_d1, col_d2 = st.columns([3, 2])
    with col_d1:
        st.markdown(f"### Observation {obs.id}")
        st.markdown(
            f"**Triage Level:** `{obs.priority_level}` (Score: `{obs.priority_score:.4f}`) | "
            f"**Cluster Group:** `ID #{obs.cluster_id}` (Size: {obs.cluster_size})"
        )
        
        st.markdown("#### Primary Attributes")
        attr_df = pd.DataFrame([
            {"Attribute": "Latitude", "Value": str(obs.latitude)},
            {"Attribute": "Longitude", "Value": str(obs.longitude)},
            {"Attribute": "Acquisition UTC", "Value": obs.acq_datetime},
            {"Attribute": "Satellite & Sensor", "Value": f"{obs.satellite} ({obs.instrument})"},
            {"Attribute": "Confidence", "Value": f"{obs.confidence_category} ({obs.confidence_normalized*100:.1f}%)"},
            {"Attribute": "Fire Radiative Power (FRP)", "Value": f"{obs.frp:.1f} MW" if obs.frp is not None else "Unavailable"},
            {"Attribute": "Brightness (Kelvin)", "Value": f"{obs.brightness_kelvin:.1f} K" if obs.brightness_kelvin else "N/A"},
            {"Attribute": "Day / Night Pass", "Value": "Day (D)" if obs.daynight == "D" else ("Night (N)" if obs.daynight == "N" else "N/A")},
            {"Attribute": "Administrative Region", "Value": obs.administrative_region},
            {"Attribute": "Jurisdiction", "Value": obs.jurisdiction},
        ])
        st.table(attr_df)

        with st.expander("View Raw Source CSV Attributes (Preserved Exactly)"):
            st.json(obs.raw_data)

    with col_d2:
        st.markdown("### Submit Human Review")
        st.caption(
            "Authorised human assessment. Reviewer judgements are recorded in persistent SQLite "
            "with a tamper-evident audit history."
        )

        with st.form(key=f"form_review_{obs.id}"):
            reviewer_id = st.text_input("Reviewer Identifier / Account:", value="analyst_desk_01")
            
            review_status = st.selectbox(
                "Review Assessment Status:",
                [
                    "Confirmed fire based on available evidence",
                    "Likely fire; additional verification needed",
                    "Possible false alarm",
                    "Non-fire thermal source",
                    "Unable to determine",
                    "Awaiting review"
                ]
            )
            
            assessment_conf = st.selectbox(
                "Assessment Confidence:",
                ["high", "medium", "low"],
                index=1
            )
            
            notes = st.text_area(
                "Review Notes & Corroborating Evidence:",
                placeholder="e.g. Visible plume on satellite RGB layer, known agricultural harvest season, industrial furnace proximity..."
            )

            submit_btn = st.form_submit_button("Record Assessment", type="primary")
            if submit_btn:
                if not reviewer_id.strip():
                    st.error("Reviewer identifier is required.")
                else:
                    rec = db.save_review(
                        observation_id=obs.id,
                        reviewer_id=reviewer_id.strip(),
                        status=review_status,
                        assessment_confidence=assessment_conf,
                        notes=notes.strip() if notes else None
                    )
                    st.success(f"Feedback successfully saved! (Correction flag: {rec['is_correction']})")

    st.markdown("---")
    st.markdown("#### Chronological Audit History for this Observation")
    history = db.get_reviews_for_observation(obs.id)
    if history:
        st.dataframe(pd.DataFrame(history), use_container_width=True)
    else:
        st.caption("No prior reviews recorded for this detection.")


# ==============================================================================
# VIEW 6: FEEDBACK & REVIEW HISTORY
# ==============================================================================
def render_feedback_history(db: DatabaseManager):
    st.subheader("Global Review Feedback & Audit History")

    all_reviews = db.get_all_reviews()
    if not all_reviews:
        st.info("No human reviews have been logged in the database yet.")
        return

    df_rev = pd.DataFrame(all_reviews)
    
    st.write(f"Total reviews logged: **{len(df_rev)}**")

    # Status distribution
    status_counts = df_rev["status"].value_counts().reset_index()
    status_counts.columns = ["Status", "Count"]
    st.dataframe(status_counts, use_container_width=True)

    st.markdown("#### Complete Feedback Audit Log")
    st.dataframe(df_rev, use_container_width=True)

    # Export CSV
    buf = io.StringIO()
    df_rev.to_csv(buf, index=False)
    st.download_button(
        label="Export Feedback History (CSV)",
        data=buf.getvalue(),
        file_name=f"firewatch_feedback_history_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )


# ==============================================================================
# VIEW 7: AUTHORITY DIRECTORY
# ==============================================================================
def render_authority_directory(db: DatabaseManager):
    st.subheader("Configured Authority & Emergency Directory")

    st.warning(
        "Notice: Production contacts must be verified independently. "
        "Default pre-loaded authority contacts are strictly designated as TEST DATA.",
        icon="⚠️"
    )

    authorities = db.get_all_authorities()
    df_auth = pd.DataFrame(authorities)
    st.dataframe(df_auth, use_container_width=True)

    with st.expander("Add or Update Authority Contact"):
        with st.form("form_add_authority"):
            auth_id = st.text_input("Authority ID (e.g. auth_karnataka_forest):")
            name = st.text_input("Authority Name:")
            jurisdiction = st.text_input("Jurisdiction Description:")
            region = st.text_input("Administrative Region (e.g. Karnataka State):")
            channel = st.selectbox("Dispatch Channel:", ["simulation", "email", "webhook"])
            contact_details = st.text_input("Contact Details (e.g. internal queue, email, or URL):")
            is_active = st.checkbox("Active Status", value=True)
            is_test = st.checkbox("Mark as Test Data", value=True)

            if st.form_submit_button("Save Authority Entry"):
                if auth_id and name:
                    db.add_or_update_authority(
                        auth_id=auth_id.strip(),
                        name=name.strip(),
                        jurisdiction=jurisdiction.strip(),
                        region=region.strip(),
                        channel=channel,
                        contact_details=contact_details.strip(),
                        active=is_active,
                        is_test_data=is_test
                    )
                    st.success(f"Authority '{name}' successfully saved.")
                    st.rerun()
                else:
                    st.error("Authority ID and Name are required.")


# ==============================================================================
# VIEW 8: NOTIFICATION CENTRE
# ==============================================================================
def render_notification_centre(db: DatabaseManager, notif_manager: NotificationManager, settings: AppSettings):
    st.subheader("Notification Centre & Audit Log")

    col_s1, col_s2 = st.columns([2, 1])
    with col_s1:
        st.info(
            f"**Notification Mode:** `{'SIMULATION MODE (Active - No real alerts sent)' if settings.notifications.simulation_mode else 'AUTHORIZED REAL DELIVERY (Live)'}`"
        )
    with col_s2:
        st.caption("All dispatches are recorded in persistent SQLite with full message payloads.")

    logs = db.get_notification_logs(limit=200)
    if not logs:
        st.info("No notifications generated yet.")
        return

    df_logs = pd.DataFrame(logs)
    st.dataframe(
        df_logs[["id", "observation_id", "recipient", "channel", "status", "priority_score", "created_at", "provider_response"]],
        use_container_width=True
    )

    # Detailed Inspection
    with st.expander("Inspect Notification Message Payload"):
        sel_alert = st.selectbox("Select Alert ID:", [l["id"] for l in logs])
        match_log = next((l for l in logs if l["id"] == sel_alert), None)
        if match_log:
            st.json(match_log)

    # Export Audit Log
    buf = io.StringIO()
    df_logs.to_csv(buf, index=False)
    st.download_button(
        label="Export Notification Audit Logs (CSV)",
        data=buf.getvalue(),
        file_name=f"firewatch_notification_audit_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )


# ==============================================================================
# VIEW 9: DATA VALIDATION REPORT
# ==============================================================================
def render_validation_report():
    st.subheader("Data Validation & Quality Audit Report")

    report: Optional[ValidationReport] = st.session_state.get("validation_report", None)
    if not report:
        st.info("No validation report in session. Load or ingest a CSV dataset in the 'Data Ingestion' tab.")
        return

    st.markdown(f"### Dataset: `{report.dataset_name}` ({report.source_product})")
    st.caption(f"Validation Timestamp: {report.import_timestamp} | Attribution: {report.attribution}")

    col_v1, col_v2, col_v3, col_v4 = st.columns(4)
    col_v1.metric("Total Rows", report.total_rows)
    col_v2.metric("Valid Rows Accepted", report.valid_rows)
    col_v3.metric("Invalid Rows Flagged", report.invalid_rows)
    col_v4.metric("Duplicate Rows", report.duplicate_rows)

    st.markdown("#### Missing Field Frequencies")
    if report.missing_field_counts:
        missing_df = pd.DataFrame(list(report.missing_field_counts.items()), columns=["Field", "Missing Count"])
        st.dataframe(missing_df, use_container_width=True)
    else:
        st.success("No missing required values detected across ingested fields.")

    st.markdown("#### Rejection Reasons & Issues Audit")
    if report.rejection_reasons:
        rejections_df = pd.DataFrame([
            {"Row": r.row_number, "Field": r.field or "N/A", "Reason": r.reason}
            for r in report.rejection_reasons
        ])
        st.dataframe(rejections_df, use_container_width=True)
    else:
        st.success("Zero rejections! All rows conformed to FIRMS operational bounds.")

    # Export Validation Report JSON & CSV
    rep_dict = report.model_dump()
    st.download_button(
        label="Download Full Validation Report (JSON)",
        data=json.dumps(rep_dict, indent=2),
        file_name=f"validation_report_{report.dataset_name}.json",
        mime="application/json"
    )


# ==============================================================================
# VIEW 10: EVALUATION & TESTING
# ==============================================================================
def render_evaluation_testing():
    st.subheader("Automated Testing Suite & Reproducible Evaluation")

    st.warning(
        "Important Evaluation Clarification: Automated unit and integration test success verifies "
        "decision-support algorithmic determinism, schema validation, and safe error handling. "
        "It does NOT represent real-world ground-truth wildfire detection accuracy, as satellite "
        "thermal anomalies require independent ground and meteorological verification.",
        icon="⚖️"
    )

    if st.button("Run Full Test Suite via Pytest", type="primary"):
        import pytest
        import sys

        with st.spinner("Executing Pytest across all test modules..."):
            # Capture output
            old_stdout = sys.stdout
            sys.stdout = buffer = io.StringIO()
            ret_code = pytest.main(["-v", "tests"])
            sys.stdout = old_stdout

            output_text = buffer.getvalue()
            if ret_code == 0:
                st.success("All 26 automated tests PASSED successfully!")
            else:
                st.error("One or more tests failed.")
            st.code(output_text)

    st.markdown("---")
    st.markdown("#### Test Suite Architecture & Verification Coverage")
    st.table(pd.DataFrame([
        {"Module": "tests/test_validator.py", "Focus": "CSV column mapping, coordinates bounds [-90,90], date/time parsing, duplicate prevention, synthetic edge cases", "Tests": 9},
        {"Module": "tests/test_priority.py", "Focus": "Score determinism, missing FRP neutral fallback, configurable weights, review threshold categories", "Tests": 4},
        {"Module": "tests/test_clustering.py", "Focus": "Haversine distance, DBSCAN spatial grouping, cluster metrics preservation", "Tests": 3},
        {"Module": "tests/test_feedback.py", "Focus": "SQLite review persistence, audit trail preservation, correction flags", "Tests": 1},
        {"Module": "tests/test_notifications.py", "Focus": "Standardized notice formatting, simulation mode isolation, duplicate cooldown throttling, SMTP failure safety", "Tests": 4},
        {"Module": "tests/test_context.py", "Focus": "Administrative bounding box resolution, non-fabrication 'Jurisdiction unknown' fallback", "Tests": 3},
        {"Module": "tests/test_privacy_security.py", "Focus": "Secret masking, no hardcoded API keys or passwords", "Tests": 2},
    ]))


# ==============================================================================
# VIEW 11: SETTINGS & ABOUT
# ==============================================================================
def render_settings_about(settings: AppSettings):
    st.subheader("System Settings, Configuration & Attribution")

    col_cfg1, col_cfg2 = st.columns(2)
    with col_cfg1:
        st.markdown("#### Priority Scoring Weights")
        st.caption("Adjustable triage ranking weights (normalized during calculation).")
        st.write(f"- Confidence Weight: `{settings.scoring.weight_confidence}`")
        st.write(f"- FRP Weight: `{settings.scoring.weight_frp}`")
        st.write(f"- Recency Weight: `{settings.scoring.weight_recency}`")
        st.write(f"- Cluster Weight: `{settings.scoring.weight_cluster}`")
        st.write(f"- Repeat Detection Weight: `{settings.scoring.weight_repeat}`")
        st.write(f"- Reference FRP: `{settings.scoring.frp_reference_mw} MW`")
        st.write(f"- Recency Window: `{settings.scoring.recency_window_hours} Hours`")

    with col_cfg2:
        st.markdown("#### Spatial Clustering Parameters")
        st.write(f"- Enabled: `{settings.clustering.enabled}`")
        st.write(f"- Epsilon: `{settings.clustering.eps_km} km` (Haversine great-circle)")
        st.write(f"- Min Samples: `{settings.clustering.min_samples}`")

        st.markdown("#### Notification Mode")
        st.write(f"- Simulation Mode: `{settings.notifications.simulation_mode}`")
        st.write(f"- Max Retries: `{settings.notifications.max_retries}`")

    st.markdown("---")
    st.markdown("#### Data Attribution & Licensing")
    st.info(
        "NASA FIRMS data courtesy of NASA Earth Science Data and Information System (ESDIS) "
        "and Land, Atmosphere Near real-time Capability for EOS (LANCE). "
        "Operated under NASA Open Data Policy (public domain / open for scientific and commercial use). "
        "https://firms.modaps.eosdis.nasa.gov/"
    )


# ==============================================================================
# VIEW 12: AUTONOMOUS SATELLITE FIRE SCANNER & LIVE DISPATCH
# ==============================================================================
def render_autonomous_pipeline(settings: AppSettings, db: DatabaseManager):
    from firewatch.automation import AutonomousFireEngine

    st.subheader("⚡ Autonomous Satellite Fire Monitor & Auto-Dispatch")
    
    st.info(
        "**Fully Automated Pipeline**: Directly downloads satellite observations from NASA FIRMS, "
        "identifies thermal fire anomalies, acquires optical satellite imagery snapshots with coordinate overlays, "
        "and automatically dispatches emergency alerts to the configured authority email."
    )

    # Config overview cards
    col_c1, col_c2, col_c3 = st.columns(3)
    sender_mail = settings.notifications.smtp_from_email or "mjdp4317@gmail.com"
    receiver_mail = settings.notifications.emergency_receiver_email or "mjdp8086@gmail.com"

    col_c1.metric("Configured Sender", sender_mail)
    col_c2.metric("Emergency Responder", receiver_mail)
    has_pwd = bool(settings.notifications.smtp_password or st.session_state.get("user_app_password"))
    col_c3.metric(
        "Live Dispatch Ready",
        "READY (Credentials Set)" if has_pwd else "SIMULATION ONLY",
        delta="Active Gmail SMTP" if has_pwd else "Need App Password"
    )

    # Live Alert Dispatch Configuration Drawer
    with st.expander("⚙️ Live Alert Credentials & Mobile Dispatch (Email / SMS / WhatsApp)", expanded=not has_pwd):
        st.markdown("#### Live Gmail & Mobile Alert Credentials")
        st.caption(
            "To send genuine emails from `mjdp4317@gmail.com` to `mjdp8086@gmail.com`, Google requires a free 16-character **App Password** "
            "(Google blocks direct password logins for third-party scripts). Generate one in 30 seconds at: "
            "[https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)"
        )

        col_g1, col_g2 = st.columns(2)
        with col_g1:
            entered_pwd = st.text_input(
                "Gmail 16-Character App Password:",
                type="password",
                value=st.session_state.get("user_app_password", os.getenv("SMTP_PASSWORD", "")),
                placeholder="xxxx xxxx xxxx xxxx",
                help="16-character password generated from Google Security App Passwords"
            )
            if entered_pwd:
                st.session_state["user_app_password"] = entered_pwd.strip().replace(" ", "")
                settings.notifications.smtp_password = entered_pwd.strip().replace(" ", "")
                settings.notifications.simulation_mode = False

        with col_g2:
            mobile_nums = st.text_input(
                "Emergency Mobile Numbers (for SMS / WhatsApp):",
                value="9705447958, 7793956633"
            )

        col_t1, col_t2 = st.columns(2)
        with col_t1:
            if st.button("✉️ Send Live Test Fire Alert Email to mjdp8086@gmail.com"):
                active_pwd = st.session_state.get("user_app_password", settings.notifications.smtp_password)
                if not active_pwd or active_pwd.strip() == "" or "example" in active_pwd:
                    st.error("Please enter your 16-character Gmail App Password above to send a real email.")
                else:
                    with st.spinner("Connecting to smtp.gmail.com:587 and dispatching test alert with satellite snapshot..."):
                        from firewatch.notifications.providers import SmtpNotificationProvider
                        from firewatch.data.imagery import SatelliteImageryManager
                        
                        test_img = SatelliteImageryManager.fetch_satellite_snapshot(18.52, 73.85, "test_live_alert", frp=65.0, confidence_pct=95.0)
                        smtp = SmtpNotificationProvider(
                            host="smtp.gmail.com",
                            port=587,
                            username=sender_mail,
                            password=active_pwd,
                            from_email=sender_mail
                        )
                        test_body = (
                            "========================================================\n"
                            "FIREWATCH AI - EMERGENCY ACTIVE FIRE ALERT\n"
                            "========================================================\n"
                            "Notice ID: ALERT-LIVE-TEST-001\n"
                            "Target Authority: Emergency Response System (mjdp8086@gmail.com)\n"
                            "Coordinates: 18.5204° N, 73.8567° E\n"
                            "Thermal Radiation (FRP): 65.0 MW (Elevated Active Fire)\n"
                            "Satellite Sensor: NASA Terra/Aqua MODIS\n"
                            "Status: IMMEDIATE VERIFICATION REQUIRED\n"
                            "\n"
                            "A high-resolution optical satellite snapshot with hotspot crosshairs\n"
                            "has been attached to this email.\n"
                            "========================================================\n"
                        )
                        res = smtp.send_notification(
                            recipient=receiver_mail,
                            subject="🔥 [FIREWATCH EMERGENCY] Active Satellite Fire Warning Detected!",
                            message_body=test_body,
                            payload_data={"latitude": 18.5204, "longitude": 73.8567},
                            image_path=test_img
                        )
                        if res.success and res.status == "delivered":
                            st.success(f"✓ {res.provider_response} Check the inbox of {receiver_mail} now!")
                        else:
                            st.error(f"Dispatch failed: {res.error or res.provider_response}")

        with col_t2:
            if st.button("🔔 Trigger Desktop Screen Fire Alarm"):
                import subprocess
                subprocess.Popen([
                    "powershell", "-Command",
                    "[System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms'); [System.Windows.Forms.MessageBox]::Show('FIREWATCH AI WARNING: Satellite Thermal Anomaly Detected! Coordinates: 18.52N, 73.85E. Alert dispatched to mjdp8086@gmail.com.', 'FireWatch AI Emergency Alarm', [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Warning)"
                ])
                st.success("Desktop fire alarm popup triggered on screen!")

    st.markdown("---")

    col_opt1, col_opt2, col_opt3 = st.columns(3)
    with col_opt1:
        feed_option = st.selectbox(
            "Satellite Observation Stream:",
            [
                ("modis_south_asia_24h", "NASA MODIS South Asia (Past 24h)"),
                ("viirs_south_asia_24h", "NASA VIIRS South Asia (Past 24h)"),
                ("modis_global_24h", "NASA MODIS Global (Past 24h)"),
                ("viirs_global_24h", "NASA VIIRS Global (Past 24h)")
            ],
            format_func=lambda x: x[1]
        )
    with col_opt2:
        threshold = st.slider("Triage Score Threshold (Fire Detection):", 0.30, 0.90, 0.45, 0.05)
    with col_opt3:
        max_alerts = st.number_input("Max Emergency Alerts to Generate:", min_value=1, max_value=10, value=3)

    if st.button("🚀 Run Autonomous Satellite Fire Scan & Dispatch", type="primary", use_container_width=True):
        active_pwd = st.session_state.get("user_app_password", settings.notifications.smtp_password)
        if active_pwd and active_pwd.strip() != "":
            settings.notifications.smtp_password = active_pwd.strip().replace(" ", "")
            settings.notifications.simulation_mode = False

        engine = AutonomousFireEngine(settings, db)
        with st.spinner("Autonomous Satellite Engine Running: Ingesting satellite stream, detecting fires, downloading imagery, and routing alerts..."):
            result = engine.run_autonomous_scan(
                source_feed=feed_option[0],
                priority_threshold=threshold,
                max_dispatches=int(max_alerts),
                force_dispatch=True
            )

            # Update observations session state
            if "all_observations" in result:
                st.session_state["observations"] = result["all_observations"]

            st.session_state["last_auto_result"] = result

    # Display Last Execution Results
    auto_res = st.session_state.get("last_auto_result", None)
    if auto_res:
        st.markdown("### Execution Log & Pipeline Telemetry")
        st.code("\n".join(auto_res.get("logs", [])))

        dispatches = auto_res.get("dispatches", [])
        if dispatches:
            st.markdown(f"### 🔥 Active Fire Detections & Satellite Imagery ({len(dispatches)} Processed)")

            for idx, item in enumerate(dispatches, 1):
                with st.container():
                    st.markdown(f"#### Alert #{idx}: Fire Hotspot `{item['observation_id']}`")
                    c_img, c_info = st.columns([1, 2])
                    
                    with c_img:
                        if item.get("image_path") and os.path.exists(item["image_path"]):
                            st.image(item["image_path"], caption=f"Satellite Optical Snapshot (Hotspot {item['observation_id']})", use_container_width=True)
                        else:
                            st.caption("Satellite imagery snapshot rendering...")

                    with c_info:
                        st.markdown(f"- **Coordinates:** `{item['latitude']:.4f}, {item['longitude']:.4f}`")
                        st.markdown(f"- **Assigned Region:** {item.get('region', 'Identified Region')}")
                        st.markdown(f"- **Triage Priority:** `{item['priority_level']}` (Score: `{item['priority_score']:.4f}`)")
                        st.markdown(f"- **Thermal Intensity (FRP):** `{item.get('frp', 'N/A')} MW`")
                        st.markdown(f"- **Sender Email:** `{item['sender']}`")
                        st.markdown(f"- **Recipient Emergency Unit:** `{item['recipient']}`")
                        st.markdown(f"- **Delivery Status:** `{item['status'].upper()}`")
                        st.info(f"**Provider Response:** {item['response']}")

                        # One-Click WhatsApp & SMS Dispatch
                        import requests as req_lib
                        wa_msg = f"🔥 FIREWATCH EMERGENCY ALERT! Active Satellite Fire Hotspot: {item['observation_id']} detected at coords ({item['latitude']:.4f}, {item['longitude']:.4f}) with FRP {item.get('frp', 'N/A')} MW. Region: {item.get('region', '')}. Map: https://www.openstreetmap.org/?mlat={item['latitude']}&mlon={item['longitude']}#map=12/{item['latitude']}/{item['longitude']}"
                        wa_url_1 = f"https://wa.me/919705447958?text={req_lib.utils.quote(wa_msg)}"
                        wa_url_2 = f"https://wa.me/917793956633?text={req_lib.utils.quote(wa_msg)}"
                        sms_url_1 = f"sms:+919705447958?body={req_lib.utils.quote(wa_msg)}"
                        sms_url_2 = f"sms:+917793956633?body={req_lib.utils.quote(wa_msg)}"

                        st.markdown("##### 🚨 Direct Instant Dispatch Channels:")
                        col_btn1, col_btn2 = st.columns(2)
                        with col_btn1:
                            st.link_button("📲 Send WhatsApp to 9705447958", wa_url_1, use_container_width=True)
                            st.link_button("💬 Send SMS to 9705447958", sms_url_1, use_container_width=True)
                        with col_btn2:
                            st.link_button("📲 Send WhatsApp to 7793956633", wa_url_2, use_container_width=True)
                            st.link_button("💬 Send SMS to 7793956633", sms_url_2, use_container_width=True)

                        if st.button(f"✉️ Re-send Direct Email Alert to {item['recipient']}", key=f"resend_{item['observation_id']}"):
                            from firewatch.notifications.providers import FormSubmitNotificationProvider
                            fsp = FormSubmitNotificationProvider()
                            res_fs = fsp.send_notification(
                                recipient=item['recipient'],
                                subject=f"🔥 [EMERGENCY ALERT] Active Satellite Fire at {item['latitude']:.4f}N, {item['longitude']:.4f}E",
                                message_body=wa_msg,
                                payload_data=item,
                                image_path=item.get("image_path")
                            )
                            if res_fs.success:
                                st.success(f"✓ {res_fs.provider_response}")
                            else:
                                st.error(f"Error: {res_fs.error}")

                    st.markdown("---")
        else:
            st.success("Satellite scan completed: No active thermal fires exceeded the detection threshold in this stream.")

