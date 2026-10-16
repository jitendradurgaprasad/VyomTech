"""
FireWatch AI - Satellite-Based Active Fire Observation Triage Dashboard.
Main Streamlit Application Entrypoint.
"""

import os
import streamlit as st
from firewatch.config import load_settings
from firewatch.storage.database import DatabaseManager
from firewatch.notifications.manager import NotificationManager
from firewatch.data.acquisition import FIRMSAcquisitionManager
from firewatch.data.validator import CSVValidator
from firewatch.analysis.priority import PriorityRanker
from firewatch.analysis.clustering import SpatialClusterer
from firewatch.analysis.context import GeoContextResolver
from firewatch.ui.views import (
    render_overview,
    render_data_ingestion,
    render_interactive_map,
    render_priority_queue,
    render_observation_details,
    render_feedback_history,
    render_authority_directory,
    render_notification_centre,
    render_validation_report,
    render_evaluation_testing,
    render_settings_about,
    render_autonomous_pipeline
)

st.set_page_config(
    page_title="FireWatch AI | Satellite Active Fire Triage",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize Core Services
settings = load_settings()
db = DatabaseManager(settings.database_path)
notif_manager = NotificationManager(settings.notifications, db)

# Ensure session state initialization
if "observations" not in st.session_state:
    # Attempt to load from database first
    stored_obs = db.get_all_observations()
    if stored_obs:
        st.session_state["observations"] = stored_obs
    else:
        # Pre-seed with genuine MODIS sample for immediate, reproducible demonstration
        res = FIRMSAcquisitionManager.load_local_sample("firms_modis_sample.csv")
        if res.success:
            obs, rep = CSVValidator.validate_csv(res.content, "NASA_MODIS_SouthAsia_24h")
            clusterer = SpatialClusterer(settings.clustering)
            clusterer.cluster_observations(obs)
            GeoContextResolver.enrich_observations(obs)
            ranker = PriorityRanker(settings.scoring)
            ranked = ranker.rank_observations(obs)
            db.save_observations(ranked)
            st.session_state["observations"] = ranked
            st.session_state["validation_report"] = rep
        else:
            st.session_state["observations"] = []

observations = st.session_state["observations"]

# Sidebar Navigation
with st.sidebar:
    st.title("🛰️ FireWatch AI")
    st.caption("Satellite Active Fire Observation Triage & Decision Support")

    st.markdown("---")
    
    nav_options = [
        "⚡ Autonomous Fire Monitor",
        "System Overview",
        "Data Ingestion & Import",
        "Interactive Map & Table",
        "Priority Review Queue",
        "Observation Details & Review",
        "Global Feedback History",
        "Authority Directory",
        "Notification Centre",
        "Data Validation Report",
        "Evaluation & Testing",
        "Settings & About"
    ]
    
    current_nav = st.session_state.get("nav_selection", "⚡ Autonomous Fire Monitor")
    default_index = nav_options.index(current_nav) if current_nav in nav_options else 0

    selected_nav = st.radio("Navigation", nav_options, index=default_index)
    st.session_state["nav_selection"] = selected_nav

    st.markdown("---")
    st.markdown("### Operational Status")
    st.success("Database: Connected (SQLite)")
    if settings.notifications.simulation_mode:
        st.info("Mode: SIMULATION ONLY\n(Safe sandbox dispatch)")
    else:
        st.warning("Mode: LIVE DISPATCH (Active)")

    st.caption(f"Sender: {settings.notifications.smtp_from_email or 'mjdp4317@gmail.com'}")
    st.caption(f"Authority: {settings.notifications.emergency_receiver_email or 'mjdp8086@gmail.com'}")
    st.caption(f"Active Detections: {len(observations)}")


# Dispatch Views
if selected_nav == "⚡ Autonomous Fire Monitor":
    render_autonomous_pipeline(settings, db)
elif selected_nav == "System Overview":
    render_overview(observations, db, settings)
elif selected_nav == "Data Ingestion & Import":
    render_data_ingestion(db, settings)
elif selected_nav == "Interactive Map & Table":
    render_interactive_map(observations, db)
elif selected_nav == "Priority Review Queue":
    render_priority_queue(observations, db, notif_manager)
elif selected_nav == "Observation Details & Review":
    render_observation_details(observations, db)
elif selected_nav == "Global Feedback History":
    render_feedback_history(db)
elif selected_nav == "Authority Directory":
    render_authority_directory(db)
elif selected_nav == "Notification Centre":
    render_notification_centre(db, notif_manager, settings)
elif selected_nav == "Data Validation Report":
    render_validation_report()
elif selected_nav == "Evaluation & Testing":
    render_evaluation_testing()
elif selected_nav == "Settings & About":
    render_settings_about(settings)
