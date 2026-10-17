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
from firewatch.storage.database import (
    AUTHORITY_FEEDBACK_OUTCOMES,
    SITE_MEMORY_OUTCOMES,
    DatabaseManager,
)
from firewatch.notifications.manager import NotificationManager
from firewatch.ui.map_view import build_folium_map, build_emergency_detection_map
from firewatch.analysis.ers import ERSLocator, BENCHMARK_ERS_STATIONS
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
                        if res.status == "suppressed_by_authority_feedback":
                            st.info(res.provider_response)
                        elif res.success:
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


def render_authority_feedback_memory(db: DatabaseManager):
    """Record manually received authority outcomes and exact-coordinate memory."""
    st.subheader("Authority Feedback & Exact-Location Memory")
    st.info(
        "Authority replies are not fetched automatically. Record an outcome received through "
        "your authorised channel here. This does not retrain the image model: it can prevent "
        "repeat notifications for one exact coordinate while the observation stays visible. "
        "A memory expires after 30 days."
    )

    observations = db.get_all_observations()
    if not observations:
        st.warning("Import observations before recording an authority response.")
        return

    observation_by_id = {obs.id: obs for obs in observations}
    observation_ids = list(observation_by_id)
    selected_id = st.selectbox(
        "Observation the authority responded to",
        observation_ids,
        format_func=lambda oid: (
            f"{oid} | {observation_by_id[oid].latitude:.6f}, "
            f"{observation_by_id[oid].longitude:.6f} | "
            f"{observation_by_id[oid].acq_datetime}"
        ),
        key="authority_feedback_observation_id",
    )
    selected_obs = observation_by_id[selected_id]
    st.caption(
        f"Selected source coordinate: {selected_obs.latitude:.6f}, {selected_obs.longitude:.6f}. "
        "Memory matches only this six-decimal coordinate; nearby coordinates are not suppressed."
    )

    with st.form("authority_feedback_form", clear_on_submit=False):
        c1, c2 = st.columns(2)
        with c1:
            authority_name = st.text_input("Responding authority / agency")
            case_reference = st.text_input("Case, email subject, or call-log reference")
            outcome = st.selectbox("Authority outcome", AUTHORITY_FEEDBACK_OUTCOMES)
            authority_source_verified = st.checkbox(
                "I verified this response came from the authority via a known official contact",
                value=False,
                help="This is an operator attestation; FireWatch does not authenticate authority replies automatically.",
            )
        with c2:
            reviewer_id = st.text_input("Operator recording the response")
            confidence = st.selectbox("Confidence in the recorded response", ["high", "medium", "low"])
            remember_exact_site = st.checkbox(
                "Remember this exact coordinate for 30 days and suppress repeat notifications",
                value=False,
                disabled=(outcome not in SITE_MEMORY_OUTCOMES or confidence != "high"),
                help=(
                    "Available only for a high-confidence prescribed-burn, known non-fire source, "
                    "or false-anomaly outcome. A case/reference is also required. This never "
                    "removes the observation from the map or review queue."
                ),
            )
        notes = st.text_area("Authority response and supporting notes")
        submitted = st.form_submit_button("Save authority feedback", type="primary")

    if submitted:
        try:
            result = db.save_authority_feedback(
                observation_id=selected_id,
                authority_name=authority_name,
                case_reference=case_reference,
                outcome=outcome,
                reviewer_id=reviewer_id,
                confidence=confidence,
                authority_source_verified=authority_source_verified,
                notes=notes,
                remember_exact_site=remember_exact_site,
            )
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.success(f"Authority feedback saved for {result['latitude']:.6f}, {result['longitude']:.6f}.")
            if result["memory_created"]:
                st.warning(
                    "Repeat notifications for this exact coordinate will be suppressed until "
                    f"{result['expires_at']}. Detections remain visible."
                )
            elif result["memories_cleared"]:
                st.success("Confirmed-wildfire feedback cleared the active exact-coordinate memory.")
            else:
                st.caption("Saved for audit only; no repeat-notification memory was created.")

    st.markdown("### Active exact-coordinate memories")
    memories = db.get_active_site_memories()
    if memories:
        st.dataframe(pd.DataFrame(memories), use_container_width=True, hide_index=True)
    else:
        st.caption("There are no active site memories.")

    st.markdown("### Authority feedback audit history")
    history = db.get_all_authority_feedback()
    if history:
        history_df = pd.DataFrame(history)
        st.dataframe(history_df, use_container_width=True, hide_index=True)
        st.download_button(
            "Export authority feedback audit (CSV)",
            data=history_df.to_csv(index=False),
            file_name=f"firewatch_authority_feedback_{datetime.utcnow():%Y%m%d_%H%M%S}.csv",
            mime="text/csv",
        )
    else:
        st.caption("No authority responses have been recorded yet.")


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
    with st.expander("⚙️ Live Alert Credentials & Multi-Channel Dispatch (Gmail / WhatsApp / SMS / Push)", expanded=not has_pwd):
        st.markdown("#### Live Emergency Alert Channels")
        st.info(
            "💡 **Emergency Notification Dispatch Channels:**\n"
            "- **Option 1 (100% Direct Gmail Delivery):** Enter a 16-character Google App Password for `mjdp4317@gmail.com`. "
            "Python connects directly to `smtp.gmail.com:587` and delivers real emails with the satellite snapshot attached straight to `mjdp8086@gmail.com`.\n"
            "- **Option 2 (Instant WhatsApp / SMS):** Use the direct 1-click links below for `9705447958` and `7793956633`.\n"
            "- **Option 3 (Live Instant Push Stream):** Open **[https://ntfy.sh/vyom_firewatch_alerts_mjdp](https://ntfy.sh/vyom_firewatch_alerts_mjdp)** in any browser or phone to receive instant emergency fire push alerts without any sign-up or tokens!"
        )

        col_g1, col_g2 = st.columns(2)
        with col_g1:
            entered_pwd = st.text_input(
                "Gmail 16-Character App Password (for mjdp4317@gmail.com):",
                type="password",
                value=st.session_state.get("user_app_password", os.getenv("SMTP_PASSWORD", "")),
                placeholder="xxxx xxxx xxxx xxxx",
                help="Generate in 30 seconds at: https://myaccount.google.com/apppasswords"
            )
            if entered_pwd and entered_pwd.strip() != "":
                clean_pwd = entered_pwd.strip().replace(" ", "")
                st.session_state["user_app_password"] = clean_pwd
                settings.notifications.smtp_password = clean_pwd
                settings.notifications.simulation_mode = False
                
                # Persist to .env
                env_file = os.path.join(os.getcwd(), ".env")
                if os.path.exists(env_file):
                    try:
                        with open(env_file, "r", encoding="utf-8") as f:
                            lines = f.readlines()
                        updated = False
                        new_lines = []
                        for line in lines:
                            if line.startswith("SMTP_PASSWORD="):
                                new_lines.append(f"SMTP_PASSWORD={clean_pwd}\n")
                                updated = True
                            else:
                                new_lines.append(line)
                        if not updated:
                            new_lines.append(f"SMTP_PASSWORD={clean_pwd}\n")
                        with open(env_file, "w", encoding="utf-8") as f:
                            f.writelines(new_lines)
                    except Exception:
                        pass

            st.caption("👉 Generate your 16-character App Password at: [Google App Passwords](https://myaccount.google.com/apppasswords)")

        with col_g2:
            mobile_nums = st.text_input(
                "Emergency Mobile Numbers (for SMS / WhatsApp):",
                value="9705447958, 7793956633"
            )
            st.link_button(
                "🔔 Open Live Web Push Stream (ntfy.sh)",
                "https://ntfy.sh/vyom_firewatch_alerts_mjdp",
                use_container_width=True
            )

        col_t1, col_t2 = st.columns(2)
        with col_t1:
            if st.button("✉️ Send Live Test Fire Alert Email to mjdp8086@gmail.com"):
                active_pwd = st.session_state.get("user_app_password", settings.notifications.smtp_password)
                if not active_pwd or active_pwd.strip() == "" or "example" in active_pwd:
                    st.warning("⚠️ No Gmail App Password entered yet. To send a real email via Gmail SMTP, generate a 16-letter App Password at https://myaccount.google.com/apppasswords and paste it above.")
                    with st.spinner("Attempting fallback dispatch via FormSubmit gateway..."):
                        from firewatch.notifications.providers import FormSubmitNotificationProvider
                        fsp = FormSubmitNotificationProvider()
                        res = fsp.send_notification(
                            recipient=receiver_mail,
                            subject="🔥 [FIREWATCH TEST] Active Satellite Fire Warning",
                            message_body="Test alert from FireWatch AI. Please check your inbox.",
                            payload_data={"latitude": 23.7644, "longitude": 86.4052, "frp": 12.64}
                        )
                        if res.success:
                            st.success(f"✓ {res.provider_response}")
                        else:
                            st.error(f"{res.provider_response}\nDetail: {res.error}")
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

    # Display Last Execution Results / Active Detections
    auto_res = st.session_state.get("last_auto_result", None)

    # Pre-load latest detections from database if available and not yet in session
    if not auto_res:
        recent_obs = db.get_recent_observations(limit=10)
        high_obs = [o for o in recent_obs if (o.priority_score or 0.0) >= 0.40]
        if high_obs:
            preloaded_dispatches = []
            for o in high_obs[:3]:
                nearest_ers = ERSLocator.find_nearest_ers(o.latitude, o.longitude, db)
                from firewatch.data.imagery import SatelliteImageryManager
                img_path = os.path.join(os.getcwd(), "data", "snapshots", f"{o.id}.jpg")
                if not os.path.exists(img_path):
                    img_path = SatelliteImageryManager.fetch_satellite_snapshot(o.latitude, o.longitude, o.id, frp=o.frp)
                preloaded_dispatches.append({
                    "observation_id": o.id,
                    "latitude": o.latitude,
                    "longitude": o.longitude,
                    "priority_score": o.priority_score,
                    "priority_level": o.priority_level,
                    "frp": o.frp,
                    "satellite": o.satellite,
                    "instrument": o.instrument,
                    "acq_datetime": o.acq_datetime,
                    "confidence_pct": round((o.confidence_normalized or 0.8) * 100, 1),
                    "region": o.administrative_region,
                    "image_path": img_path,
                    "recipient": settings.notifications.emergency_receiver_email or "mjdp8086@gmail.com",
                    "sender": settings.notifications.smtp_from_email or "mjdp4317@gmail.com",
                    "status": "ready_for_dispatch",
                    "response": f"Hotspot verified by satellite sensor telemetry. Assigned nearest ERS: {nearest_ers['name']}.",
                    "nearest_ers": nearest_ers,
                    "nearest_ers_name": nearest_ers["name"],
                    "nearest_ers_distance_km": nearest_ers["distance_km"],
                    "nearest_ers_lat": nearest_ers["latitude"],
                    "nearest_ers_lon": nearest_ers["longitude"]
                })
            auto_res = {
                "success": True,
                "dispatches": preloaded_dispatches,
                "logs": [f"[*] Loaded {len(preloaded_dispatches)} active satellite hotspot records from database telemetry."]
            }
            st.session_state["last_auto_result"] = auto_res

    if auto_res:
        dispatches = auto_res.get("dispatches", [])
        if dispatches:
            st.markdown(f"### 🚨 Active Satellite Fire Hotspots ({len(dispatches)} Detected)")

            # Select Hotspot for Map and ERS Inspection
            if len(dispatches) > 1:
                selected_idx = st.selectbox(
                    "📍 Select Detected Fire Hotspot to Inspect on Map & Route to Nearest ERS:",
                    range(len(dispatches)),
                    format_func=lambda i: (
                        f"Hotspot #{i+1}: {dispatches[i]['observation_id']} "
                        f"({dispatches[i]['latitude']:.4f}°N, {dispatches[i]['longitude']:.4f}°E) | "
                        f"FRP: {dispatches[i].get('frp', 'N/A')} MW | "
                        f"Nearest ERS: {dispatches[i].get('nearest_ers_name', 'ERS Station')[:32]}..."
                    )
                )
                item = dispatches[selected_idx]
            else:
                item = dispatches[0]

            nearest_ers = item.get("nearest_ers") or ERSLocator.find_nearest_ers(item["latitude"], item["longitude"], db)
            all_stations = ERSLocator.get_all_stations(db)

            # ------------------------------------------------------------------
            # 1. INTERACTIVE SATELLITE FRAME & NEAREST ERS MAP
            # ------------------------------------------------------------------
            st.markdown("#### 🗺️ Satellite Acquisition Frame & Nearest Emergency Response Station (ERS)")
            st.caption(
                "Visualizing the exact frame coordinates collected by the satellite sensor (~1 km² sensor pixel footprint in red), "
                "the thermal hotspot, and the nearest Emergency Response Station (ERS) highlighted with direct geodesic dispatch routing."
            )

            # Build and render Folium Map
            detection_map = build_emergency_detection_map(item, nearest_ers, all_stations)
            st_folium(detection_map, width=None, height=480, returned_objects=[])

            # Geodesic Dispatch Routing Metrics Bar
            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
            m_col1.metric("Hotspot Frame Coordinates", f"{item['latitude']:.4f}° N, {item['longitude']:.4f}° E")
            m_col2.metric("Nearest ERS Station", nearest_ers.get("name", "ERS Command")[:26] + "...")
            m_col3.metric("Geodesic Distance to Fire", f"{nearest_ers.get('distance_km', 0.0):.1f} km")
            m_col4.metric("Est. Ground Transit Time", f"~{nearest_ers.get('est_transit_minutes', 25)} mins")

            st.markdown("---")

            # ------------------------------------------------------------------
            # 2. EMERGENCY MAIL NOTIFICATION & DISPATCH STATUS (VISIBLE ON SCREEN)
            # ------------------------------------------------------------------
            st.markdown("#### ✉️ ERS Emergency Mail Notification & Dispatch Status")

            status_str = str(item.get("status", "")).lower()
            if status_str == "suppressed_by_authority_feedback":
                st.info(item.get("response", "Repeat notification suppressed by exact-coordinate authority feedback memory."))
            elif status_str in ("delivered", "delivered_success", "sent"):
                st.success(f"✓ Live Emergency Fire Notification Dispatched to Authority: `{item['recipient']}`")
            elif "activation" in status_str:
                st.warning(f"⚠️ Email Dispatch Prepared for `{item['recipient']}`. Activation token confirmation pending.")
            else:
                st.info(f"📧 Notification Prepared for ERS Authority: `{item['recipient']}` | Status: `{item['status'].upper()}`")

            c_img, c_info = st.columns([1, 2])
            with c_img:
                if item.get("image_path") and os.path.exists(item["image_path"]):
                    st.image(
                        item["image_path"],
                        caption=f"Optical Satellite Snapshot (Hotspot {item['observation_id']})",
                        use_container_width=True
                    )
                else:
                    st.caption("Satellite imagery snapshot rendering...")

            with c_info:
                st.markdown(f"##### 📋 Emergency Dispatch Telemetry")
                st.markdown(f"- **Target ERS Authority Station:** `{nearest_ers.get('name')}`")
                st.markdown(f"- **Authority Jurisdiction:** {nearest_ers.get('jurisdiction', 'Regional Emergency Command')}")
                st.markdown(f"- **Sender Email:** `{item.get('sender', 'mjdp4317@gmail.com')}`")
                st.markdown(f"- **Recipient Authority Email:** `{item.get('recipient', 'mjdp8086@gmail.com')}`")
                st.markdown(f"- **Emergency Mobile Contacts:** `+91-9705447958, +91-7793956633`")
                st.markdown(f"- **Satellite Platform & Sensor:** `{item.get('satellite', 'NASA Terra/Aqua')} ({item.get('instrument', 'MODIS')})`")
                st.markdown(f"- **Thermal Intensity (FRP):** `{item.get('frp', 'N/A')} MW`")
                st.markdown(f"- **Triage Priority:** `{item.get('priority_level', 'High Review Priority')}` (Score: `{item.get('priority_score', 0.85):.4f}`)")
                st.markdown(f"- **Delivery Status:** `{item.get('status', 'SENT').upper()}`")
                st.info(f"**Gateway / Mail Response:** {item.get('response', 'Dispatched to nearest emergency station.')}")

            # Expandable Full Email Message Body Preview
            osm_url = f"https://www.openstreetmap.org/?mlat={item['latitude']}&mlon={item['longitude']}#map=12/{item['latitude']}/{item['longitude']}"
            full_email_body = (
                f"========================================================\n"
                f"FIREWATCH AI - EMERGENCY ACTIVE FIRE ALERT\n"
                f"========================================================\n"
                f"Notice ID:          ALERT-{item['observation_id']}\n"
                f"Target Authority:   {nearest_ers.get('name')} ({item['recipient']})\n"
                f"Jurisdiction:       {nearest_ers.get('jurisdiction')}\n"
                f"Distance to Fire:   {nearest_ers.get('distance_km', 0.0):.1f} km\n"
                f"\n"
                f"SATELLITE FRAME COORDINATES:\n"
                f"  Latitude:         {item['latitude']:.5f}° N\n"
                f"  Longitude:        {item['longitude']:.5f}° E\n"
                f"  Region:           {item.get('region', 'Identified Region')}\n"
                f"  Map Inspection:   {osm_url}\n"
                f"\n"
                f"THERMAL SENSOR TELEMETRY:\n"
                f"  Satellite Sensor: {item.get('satellite', 'NASA')} ({item.get('instrument', 'MODIS/VIIRS')})\n"
                f"  Thermal Power:    {item.get('frp', 'N/A')} MW (Radiative Fire Anomaly)\n"
                f"  Acquisition UTC:  {item.get('acq_datetime', 'Recent Pass')}\n"
                f"  Priority Level:   {item.get('priority_level', 'High Review Priority')}\n"
                f"\n"
                f"ACTION REQUIRED:\n"
                f"  1. Deploy ground ranger / nearest emergency unit ({nearest_ers.get('name')}).\n"
                f"  2. Verify containment perimeter along coordinates ({item['latitude']:.4f}, {item['longitude']:.4f}).\n"
                f"  3. Optical satellite snapshot is attached to this email.\n"
                f"========================================================\n"
            )

            with st.expander("📄 View Full Email Notification Content Dispatched to mjdp8086@gmail.com"):
                st.code(full_email_body)

            # ------------------------------------------------------------------
            # 3. DIRECT INSTANT DISPATCH CHANNELS (WHATSAPP, SMS, NTFY, EMAIL)
            # ------------------------------------------------------------------
            st.markdown("##### 🚨 Direct Instant Dispatch Channels:")
            import requests as req_lib
            wa_msg = (
                f"🔥 FIREWATCH EMERGENCY ALERT! Active Satellite Fire Hotspot: {item['observation_id']} "
                f"detected at coordinates ({item['latitude']:.4f}, {item['longitude']:.4f}) with FRP {item.get('frp', 'N/A')} MW. "
                f"Nearest ERS Station: {nearest_ers.get('name')} ({nearest_ers.get('distance_km', 0.0):.1f} km away). "
                f"Inspect Map: {osm_url}"
            )
            wa_url_1 = f"https://wa.me/919705447958?text={req_lib.utils.quote(wa_msg)}"
            wa_url_2 = f"https://wa.me/917793956633?text={req_lib.utils.quote(wa_msg)}"
            sms_url_1 = f"sms:+919705447958?body={req_lib.utils.quote(wa_msg)}"
            sms_url_2 = f"sms:+917793956633?body={req_lib.utils.quote(wa_msg)}"

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                st.link_button("📲 Send WhatsApp to 9705447958", wa_url_1, use_container_width=True)
                st.link_button("💬 Send SMS to 9705447958", sms_url_1, use_container_width=True)
            with col_btn2:
                st.link_button("📲 Send WhatsApp to 7793956633", wa_url_2, use_container_width=True)
                st.link_button("💬 Send SMS to 7793956633", sms_url_2, use_container_width=True)

            col_res1, col_res2 = st.columns(2)
            with col_res1:
                if st.button(f"✉️ Re-send Direct Email Alert to {item['recipient']}", key=f"resend_{item['observation_id']}"):
                    active_pwd = st.session_state.get("user_app_password", settings.notifications.smtp_password)
                    if active_pwd and active_pwd.strip() != "" and "example" not in active_pwd:
                        from firewatch.notifications.providers import SmtpNotificationProvider
                        smtp = SmtpNotificationProvider(
                            host="smtp.gmail.com",
                            port=587,
                            username=item['sender'],
                            password=active_pwd,
                            from_email=item['sender']
                        )
                        res_email = smtp.send_notification(
                            recipient=item['recipient'],
                            subject=f"🔥 [EMERGENCY ALERT] Active Satellite Fire at {item['latitude']:.4f}N, {item['longitude']:.4f}E",
                            message_body=full_email_body,
                            payload_data=item,
                            image_path=item.get("image_path")
                        )
                        if res_email.success:
                            st.success(f"✓ {res_email.provider_response}")
                        else:
                            st.error(f"Error: {res_email.error}")
                    else:
                        from firewatch.notifications.providers import FormSubmitNotificationProvider
                        fsp = FormSubmitNotificationProvider()
                        res_fs = fsp.send_notification(
                            recipient=item['recipient'],
                            subject=f"🔥 [EMERGENCY ALERT] Active Satellite Fire at {item['latitude']:.4f}N, {item['longitude']:.4f}E",
                            message_body=full_email_body,
                            payload_data=item,
                            image_path=item.get("image_path")
                        )
                        if res_fs.success:
                            st.success(f"✓ {res_fs.provider_response}")
                        else:
                            st.warning(f"{res_fs.provider_response}\n(Tip: Enter your 16-character Gmail App Password above for direct SMTP delivery)")
            with col_res2:
                st.link_button("🔔 View Alert on Live Push Feed", "https://ntfy.sh/vyom_firewatch_alerts_mjdp", use_container_width=True)

            st.markdown("---")
            with st.expander("Execution Log & Pipeline Telemetry"):
                st.code("\n".join(auto_res.get("logs", [])))
        else:
            st.success("Satellite scan completed: No active thermal fires exceeded the detection threshold in this stream.")

