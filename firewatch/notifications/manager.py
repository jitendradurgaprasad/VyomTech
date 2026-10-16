"""
Notification Manager and Dispatch Workflow for FireWatch AI.
"""

from __future__ import annotations
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from firewatch.config import NotificationConfig
from firewatch.data.schemas import ObservationNormalized
from firewatch.storage.database import DatabaseManager
from firewatch.notifications.providers import (
    BaseNotificationProvider,
    SimulationNotificationProvider,
    SmtpNotificationProvider,
    WebhookNotificationProvider,
    NotificationResult
)


class NotificationManager:
    """Orchestrates notification triggers, location-aware authority routing, and audits."""

    def __init__(self, config: NotificationConfig, db: DatabaseManager):
        self.config = config
        self.db = db

    def get_provider_for_channel(self, channel: str) -> BaseNotificationProvider:
        """Select provider based on simulation mode and channel."""
        if self.config.simulation_mode:
            return SimulationNotificationProvider()

        ch_lower = channel.lower()
        if ch_lower == "email":
            return SmtpNotificationProvider(
                host=self.config.smtp_server,
                port=self.config.smtp_port,
                username=self.config.smtp_username,
                password=self.config.smtp_password,
                from_email=self.config.smtp_from_email or "alerts@firewatch.ai"
            )
        elif ch_lower == "webhook":
            return WebhookNotificationProvider(
                webhook_url=self.config.webhook_url,
                secret=self.config.webhook_secret
            )
        else:
            return SimulationNotificationProvider()

    def route_authority_for_observation(self, obs: ObservationNormalized) -> Dict[str, Any]:
        """
        Associate observation with an appropriate authority.
        If jurisdiction cannot be determined reliably, routes to the Central Review Queue.
        """
        authorities = self.db.get_all_authorities()
        active_authorities = [a for a in authorities if a.get("active", 1)]

        # 1. Match by administrative region
        if obs.administrative_region and obs.administrative_region != "Unknown":
            for auth in active_authorities:
                if auth.get("region", "").lower() == obs.administrative_region.lower():
                    return auth

        # 2. Match by jurisdiction keyword
        if obs.jurisdiction and "unknown" not in obs.jurisdiction.lower():
            for auth in active_authorities:
                if auth.get("jurisdiction", "").lower() in obs.jurisdiction.lower():
                    return auth

        # 3. Fallback: Central Review Queue
        for auth in active_authorities:
            if "central" in auth.get("id", "").lower() or "central" in auth.get("name", "").lower():
                return auth

        # Default fallback dict
        return {
            "id": "auth_central_default",
            "name": "Central Review Desk (Fallback)",
            "jurisdiction": "National / Central Queue",
            "region": "Unassigned",
            "channel": "simulation",
            "contact_details": "internal-queue://triage-central@firewatch.sim",
            "active": 1,
            "is_test_data": 1
        }

    @staticmethod
    def construct_notification_payload(
        obs: ObservationNormalized,
        authority: Dict[str, Any],
        trigger_reason: str,
        alert_id: str
    ) -> Tuple[str, str, Dict[str, Any]]:
        """
        Construct structured, standardized notification text and data payload.
        Clearly highlights uncertainty, caveats, and recommended human verification steps.
        """
        subject = f"[FireWatch Review Notice] {obs.priority_level or 'Observation Triage'} - {obs.id}"
        osm_link = f"https://www.openstreetmap.org/?mlat={obs.latitude}&mlon={obs.longitude}#map=12/{obs.latitude}/{obs.longitude}"

        reasons_bulleted = "\n".join(f"  * {r}" for r in (obs.priority_reasons or []))
        if not reasons_bulleted:
            reasons_bulleted = "  * Prioritized based on standard algorithmic observation factors."

        limitations_bulleted = "\n".join(f"  * {l}" for l in (obs.priority_limitations or []))

        message = (
            f"========================================================\n"
            f"FIREWATCH AI - SATELLITE OBSERVATION REVIEW NOTICE\n"
            f"========================================================\n"
            f"Notice ID:          {alert_id}\n"
            f"Observation ID:     {obs.id}\n"
            f"Trigger Reason:     {trigger_reason}\n"
            f"Review Priority:    {obs.priority_level} (Score: {obs.priority_score:.4f} / 1.0000)\n"
            f"\n"
            f"GEOGRAPHIC LOCATION:\n"
            f"  Latitude:         {obs.latitude:.5f}\n"
            f"  Longitude:        {obs.longitude:.5f}\n"
            f"  Assigned Region:  {obs.administrative_region}\n"
            f"  Jurisdiction:     {obs.jurisdiction}\n"
            f"  Map Inspection:   {osm_link}\n"
            f"\n"
            f"SATELLITE SENSOR TELEMETRY:\n"
            f"  Sensor/Product:   {obs.instrument} ({obs.satellite})\n"
            f"  Acquisition UTC:  {obs.acq_datetime}\n"
            f"  Confidence Level: {obs.confidence_category.upper()} ({obs.confidence_normalized * 100:.1f}%)\n"
            f"  Radiative Power:  {f'{obs.frp:.1f} MW' if obs.frp is not None else 'N/A'}\n"
            f"  Cluster Size:     {obs.cluster_size} detections (Repeat count: {obs.repeat_detection_count})\n"
            f"\n"
            f"TRIAGE REASONS:\n"
            f"{reasons_bulleted}\n"
            f"\n"
            f"CRITICAL DISCLAIMER & SENSOR LIMITATIONS:\n"
            f"  * THIS IS AN UNVERIFIED SATELLITE THERMAL DETECTION.\n"
            f"  * NOT A CONFIRMED WILDFIRE OR EMERGENCY DISPATCH EVENT.\n"
            f"  * Thermal anomalies may represent controlled agricultural burning,\n"
            f"    industrial flare activity, or solar reflection.\n"
            f"{limitations_bulleted}\n"
            f"\n"
            f"RECOMMENDED HUMAN VERIFICATION ACTIONS:\n"
            f"  1. Cross-reference local meteorological conditions (wind speed, humidity).\n"
            f"  2. Review regional land-use classification (cropland vs protected forest).\n"
            f"  3. Dispatch ground ranger or local monitoring personnel for visual check.\n"
            f"  4. Log assessment in the FireWatch Review Dashboard.\n"
            f"========================================================\n"
        )

        payload_dict = {
            "alert_id": alert_id,
            "observation_id": obs.id,
            "latitude": obs.latitude,
            "longitude": obs.longitude,
            "acq_datetime": obs.acq_datetime,
            "satellite": obs.satellite,
            "instrument": obs.instrument,
            "confidence_normalized": obs.confidence_normalized,
            "frp": obs.frp,
            "priority_score": obs.priority_score,
            "priority_level": obs.priority_level,
            "jurisdiction": obs.jurisdiction,
            "authority_id": authority.get("id"),
            "trigger_reason": trigger_reason,
            "osm_link": osm_link
        }

        return subject, message, payload_dict

    def process_notification(
        self,
        obs: ObservationNormalized,
        trigger_reason: str = "Priority threshold exceeded",
        force: bool = False
    ) -> NotificationResult:
        """
        Evaluate and dispatch (or simulate) a notification for an observation.
        Includes duplicate throttling check and full audit persistence.
        """
        # Duplicate throttle check
        if not force and self.db.is_recently_notified(obs.id, window_minutes=60):
            return NotificationResult(
                success=False,
                status="failed",
                provider_response="THROTTLED_DUPLICATE: Observation was already notified within the last 60 minutes.",
                error="Duplicate notification prevented by cooldown policy."
            )

        alert_id = f"alert_{uuid.uuid4().hex[:10]}"
        authority = self.route_authority_for_observation(obs)
        channel = authority.get("channel", "simulation")
        recipient = authority.get("contact_details", "internal-queue@firewatch.sim")

        subject, message, payload = self.construct_notification_payload(obs, authority, trigger_reason, alert_id)
        provider = self.get_provider_for_channel(channel)

        # Dispatch
        result = provider.send_notification(
            recipient=recipient,
            subject=subject,
            message_body=message,
            payload_data=payload
        )

        # Log into audit table
        self.db.log_notification(
            notif_id=alert_id,
            observation_id=obs.id,
            authority_id=authority.get("id"),
            recipient=recipient,
            channel=channel,
            trigger_reason=trigger_reason,
            priority_score=obs.priority_score,
            status=result.status,
            provider_response=result.provider_response,
            retry_count=0,
            error_details=result.error,
            payload_summary=payload
        )

        return result
