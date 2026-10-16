"""
Autonomous Satellite Fire Detection and Automated Authority Dispatch Engine.
"""

from __future__ import annotations
import os
from typing import Dict, Any, List, Optional
from firewatch.config import AppSettings
from firewatch.data.acquisition import FIRMSAcquisitionManager
from firewatch.data.validator import CSVValidator
from firewatch.data.imagery import SatelliteImageryManager
from firewatch.data.schemas import ObservationNormalized
from firewatch.analysis.priority import PriorityRanker
from firewatch.analysis.clustering import SpatialClusterer
from firewatch.analysis.context import GeoContextResolver
from firewatch.storage.database import DatabaseManager
from firewatch.notifications.manager import NotificationManager
from firewatch.notifications.providers import NotificationResult


class AutonomousFireEngine:
    """
    End-to-End Autonomous Satellite Fire Monitor.
    Directly ingests satellite telemetry, checks for active thermal fires,
    generates satellite imagery snapshots, and automatically dispatches
    alerts to the nearest authority email.
    """

    def __init__(self, settings: AppSettings, db: DatabaseManager):
        self.settings = settings
        self.db = db
        self.notif_manager = NotificationManager(settings.notifications, db)

    def run_autonomous_scan(
        self,
        source_feed: str = "modis_south_asia_24h",
        priority_threshold: float = 0.50,
        max_dispatches: int = 5,
        force_dispatch: bool = True
    ) -> Dict[str, Any]:
        """
        Execute fully autonomous fire detection, satellite snapshot generation, and email notification.
        """
        logs: List[str] = []
        logs.append(f"[*] Starting Autonomous Satellite Fire Monitoring pipeline...")
        logs.append(f"[*] Connecting to satellite feed: {source_feed}")

        # 1. Acquire Satellite Feed
        res = FIRMSAcquisitionManager.fetch_live_feed(source_feed, timeout=12)
        if not res.success or not res.content:
            logs.append(f"[!] Live satellite feed unavailable or timed out ({res.error}). Falling back to local genuine sample.")
            sample_file = "firms_modis_sample.csv" if "modis" in source_feed else "firms_viirs_sample.csv"
            res = FIRMSAcquisitionManager.load_local_sample(sample_file)
            if not res.success:
                return {
                    "success": False,
                    "error": f"Failed to acquire satellite feed: {res.error}",
                    "logs": logs,
                    "fires_detected": 0
                }

        logs.append(f"[+] Satellite stream acquired successfully ({res.records_count} total satellite observations).")

        # 2. Validate & Ingest
        observations, report = CSVValidator.validate_csv(res.content, source_feed)
        logs.append(f"[+] Ingestion & Validation: {report.valid_rows} valid records accepted, {report.invalid_rows} rejected.")

        if not observations:
            return {
                "success": True,
                "message": "No valid satellite observations found in this pass.",
                "logs": logs,
                "fires_detected": 0,
                "dispatches": []
            }

        # 3. Spatial Clustering & Geographic Context
        clusterer = SpatialClusterer(self.settings.clustering)
        clusterer.cluster_observations(observations)
        GeoContextResolver.enrich_observations(observations)

        # 4. Explainable Priority Triage
        ranker = PriorityRanker(self.settings.scoring)
        ranked = ranker.rank_observations(observations)
        self.db.save_observations(ranked)

        # 5. Filter Active Fire Detections
        detected_fires = [
            o for o in ranked
            if (o.priority_score or 0.0) >= priority_threshold
        ]
        logs.append(f"[+] Fire Detection Analysis: Found {len(detected_fires)} active thermal fire detections exceeding threshold ({priority_threshold}).")

        # 6. Autonomous Satellite Snapshot & Email Dispatch
        dispatches: List[Dict[str, Any]] = []
        sender_email = self.settings.notifications.smtp_from_email or "mjdp4317@gmail.com"
        receiver_email = self.settings.notifications.emergency_receiver_email or "mjdp8086@gmail.com"

        logs.append(f"[*] Authority Routing: Configured sender: {sender_email} -> Emergency response: {receiver_email}")

        dispatch_targets = detected_fires[:max_dispatches]
        for idx, fire in enumerate(dispatch_targets, 1):
            logs.append(f"[*] Processing Fire #{idx} (ID: {fire.id}) at coordinates ({fire.latitude:.4f}, {fire.longitude:.4f})...")

            # Fetch optical satellite image snapshot
            img_path = SatelliteImageryManager.fetch_satellite_snapshot(
                lat=fire.latitude,
                lon=fire.longitude,
                obs_id=fire.id,
                frp=fire.frp,
                confidence_pct=fire.confidence_normalized * 100
            )
            if img_path:
                logs.append(f"    -> Satellite optical snapshot acquired: {img_path}")

            # Process location-aware notification
            trigger_reason = f"Autonomous Fire Detection Trigger: Score {fire.priority_score:.4f} (FRP: {fire.frp} MW)"
            notif_res = self.notif_manager.process_notification(
                fire,
                trigger_reason=trigger_reason,
                force=force_dispatch,
                recipient_override=receiver_email
            )

            logs.append(f"    -> Notification Status: [{notif_res.status.upper()}] - {notif_res.provider_response}")

            dispatches.append({
                "observation_id": fire.id,
                "latitude": fire.latitude,
                "longitude": fire.longitude,
                "priority_score": fire.priority_score,
                "priority_level": fire.priority_level,
                "frp": fire.frp,
                "region": fire.administrative_region,
                "image_path": img_path,
                "recipient": receiver_email,
                "sender": sender_email,
                "status": notif_res.status,
                "response": notif_res.provider_response
            })

        logs.append(f"[✓] Autonomous Fire Monitoring pass completed. Total alerts processed: {len(dispatches)}.")

        return {
            "success": True,
            "total_observations": len(ranked),
            "fires_detected": len(detected_fires),
            "dispatches": dispatches,
            "logs": logs,
            "all_observations": ranked
        }
