"""
Plotly Chart Generators for FireWatch AI.
"""

from __future__ import annotations
from typing import List, Dict, Any
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from firewatch.data.schemas import ObservationNormalized


def create_priority_distribution_chart(observations: List[ObservationNormalized]) -> go.Figure:
    """Bar chart of priority score categories."""
    if not observations:
        fig = go.Figure()
        fig.update_layout(title="No observation data available")
        return fig

    counts = {"High Review Priority": 0, "Medium Review Priority": 0, "Low Review Priority": 0}
    for obs in observations:
        lvl = obs.priority_level or "Low Review Priority"
        if lvl in counts:
            counts[lvl] += 1
        else:
            counts["Low Review Priority"] += 1

    df = pd.DataFrame({
        "Priority Level": list(counts.keys()),
        "Count": list(counts.values()),
        "Color": ["#d9534f", "#f0ad4e", "#5bc0de"]
    })

    fig = px.bar(
        df,
        x="Priority Level",
        y="Count",
        color="Priority Level",
        color_discrete_map={
            "High Review Priority": "#d9534f",
            "Medium Review Priority": "#f0ad4e",
            "Low Review Priority": "#5bc0de"
        },
        title="Active Observations by Triage Review Priority",
        text="Count"
    )
    fig.update_layout(showlegend=False, margin=dict(l=20, r=20, t=40, b=20), height=300)
    return fig


def create_frp_histogram(observations: List[ObservationNormalized]) -> go.Figure:
    """Histogram of Fire Radiative Power (MW)."""
    frps = [o.frp for o in observations if o.frp is not None]
    if not frps:
        fig = go.Figure()
        fig.update_layout(title="No FRP data available for current selection")
        return fig

    fig = px.histogram(
        x=frps,
        nbins=30,
        title="Fire Radiative Power (FRP in MW) Distribution",
        labels={"x": "FRP (MW)", "y": "Observation Count"},
        color_discrete_sequence=["#e67e22"]
    )
    fig.update_layout(margin=dict(l=20, r=20, t=40, b=20), height=300)
    return fig


def create_satellite_share_pie(observations: List[ObservationNormalized]) -> go.Figure:
    """Pie chart showing distribution across satellite platforms."""
    if not observations:
        fig = go.Figure()
        fig.update_layout(title="No satellite platform data")
        return fig

    sats = [o.satellite for o in observations]
    df = pd.DataFrame({"satellite": sats}).value_counts().reset_index()
    df.columns = ["Satellite", "Count"]

    fig = px.pie(
        df,
        names="Satellite",
        values="Count",
        title="Observations by Satellite Platform",
        hole=0.4,
        color_discrete_sequence=px.colors.qualitative.Safe
    )
    fig.update_layout(margin=dict(l=20, r=20, t=40, b=20), height=300)
    return fig


def create_confidence_vs_frp_scatter(observations: List[ObservationNormalized]) -> go.Figure:
    """Scatter plot of Confidence vs FRP colored by Priority Score."""
    valid_pts = [o for o in observations if o.frp is not None]
    if not valid_pts:
        fig = go.Figure()
        fig.update_layout(title="Insufficient FRP points for scatter analysis")
        return fig

    data = {
        "FRP": [o.frp for o in valid_pts],
        "Confidence (%)": [o.confidence_normalized * 100 for o in valid_pts],
        "Priority Score": [o.priority_score or 0.0 for o in valid_pts],
        "Satellite": [o.satellite for o in valid_pts],
        "ID": [o.id for o in valid_pts]
    }
    df = pd.DataFrame(data)

    fig = px.scatter(
        df,
        x="FRP",
        y="Confidence (%)",
        color="Priority Score",
        hover_data=["ID", "Satellite"],
        title="Confidence vs Fire Radiative Power (FRP)",
        color_continuous_scale="Viridis"
    )
    fig.update_layout(margin=dict(l=20, r=20, t=40, b=20), height=320)
    return fig
