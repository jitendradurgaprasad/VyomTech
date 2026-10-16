"""
Configuration management for FireWatch AI.
"""

from __future__ import annotations
import os
from typing import Optional
from pydantic import BaseModel, Field


class ScoringConfig(BaseModel):
    """Configurable weights and parameters for explainable priority scoring."""
    weight_confidence: float = Field(0.25, description="Weight for satellite observation confidence (0-1)")
    weight_frp: float = Field(0.30, description="Weight for Fire Radiative Power (MW)")
    weight_recency: float = Field(0.20, description="Weight for observation recency")
    weight_cluster: float = Field(0.15, description="Weight for spatial cluster size / density")
    weight_repeat: float = Field(0.10, description="Weight for multiple nearby detections within temporal window")
    
    frp_reference_mw: float = Field(50.0, description="Reference FRP in MW for non-linear saturation scaling")
    recency_window_hours: float = Field(48.0, description="Window in hours for recency decay calculation")
    high_priority_threshold: float = Field(0.70, description="Normalized score threshold for High Review Priority")
    medium_priority_threshold: float = Field(0.40, description="Normalized score threshold for Medium Review Priority")


class ClusteringConfig(BaseModel):
    """Parameters for spatial DBSCAN clustering."""
    enabled: bool = True
    eps_km: float = Field(10.0, description="Maximum distance between two samples in kilometers for clustering")
    min_samples: int = Field(2, description="Minimum number of samples required to form a cluster")


class NotificationConfig(BaseModel):
    """Notification settings and provider routing."""
    simulation_mode: bool = Field(True, description="When True, prevents sending real communications")
    smtp_server: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from_email: Optional[str] = "alerts@firewatch.ai"
    webhook_url: Optional[str] = None
    webhook_secret: Optional[str] = None
    max_retries: int = 3
    retry_backoff_seconds: int = 5


class AppSettings(BaseModel):
    """Master application configuration."""
    app_name: str = "FireWatch AI"
    environment: str = "development"
    database_path: str = "firewatch.db"
    firms_map_key: Optional[str] = None
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    clustering: ClusteringConfig = Field(default_factory=ClusteringConfig)
    notifications: NotificationConfig = Field(default_factory=NotificationConfig)

    disclaimer: str = (
        "IMPORTANT DISCLAIMER: FireWatch AI is an observation-triage and decision-support "
        "system. Satellite thermal anomaly detections are NOT ground-truth confirmations "
        "of wildfires. Detections may represent non-fire heat sources (e.g. industrial activity, "
        "gas flares, hot bare soil, prescribed agricultural burns) or be subject to false alarms. "
        "Cloud cover, tree canopy, and sensor geometry may obscure actual fires. Priority scores "
        "are human-review aids, not emergency severity assessments. This system does NOT "
        "replace trained emergency personnel or constitute an automated emergency dispatch service."
    )


def load_settings() -> AppSettings:
    """Load settings with environment variable overrides."""
    # Check for .env file if available
    env_file = ".env"
    if os.path.exists(env_file):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip()
                        if k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

    env = os.getenv("FIREWATCH_ENV", "development")
    db_path = os.getenv("DATABASE_PATH", "firewatch.db")
    map_key = os.getenv("FIRMS_MAP_KEY", None)
    
    sim_mode_str = os.getenv("NOTIFICATION_SIMULATION_MODE", "True")
    sim_mode = sim_mode_str.lower() in ("true", "1", "yes", "t")

    notification_cfg = NotificationConfig(
        simulation_mode=sim_mode,
        smtp_server=os.getenv("SMTP_SERVER"),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_username=os.getenv("SMTP_USERNAME"),
        smtp_password=os.getenv("SMTP_PASSWORD"),
        smtp_from_email=os.getenv("SMTP_FROM_EMAIL", "alerts@firewatch.ai"),
        webhook_url=os.getenv("WEBHOOK_ALERT_URL"),
        webhook_secret=os.getenv("WEBHOOK_SECRET")
    )

    return AppSettings(
        environment=env,
        database_path=db_path,
        firms_map_key=map_key,
        notifications=notification_cfg
    )
