"""
Explainable Priority Scoring Module for FireWatch AI.
"""

from __future__ import annotations
import math
from datetime import datetime
from typing import List, Dict, Any, Tuple
from firewatch.config import ScoringConfig
from firewatch.data.schemas import ObservationNormalized


class PriorityRanker:
    """
    Computes transparent, explainable priority scores for human review triage.
    Note: Review priority is a decision-support aid and does not equate to wildfire severity.
    """

    def __init__(self, config: ScoringConfig):
        self.config = config

    def calculate_observation_priority(
        self,
        obs: ObservationNormalized,
        dataset_max_time: Optional[datetime] = None
    ) -> ObservationNormalized:
        """Calculate and attach explainable score breakdown to an individual observation."""
        # 1. Normalize weights
        total_w = (
            self.config.weight_confidence +
            self.config.weight_frp +
            self.config.weight_recency +
            self.config.weight_cluster +
            self.config.weight_repeat
        )
        if total_w <= 0:
            total_w = 1.0
        w_conf = self.config.weight_confidence / total_w
        w_frp = self.config.weight_frp / total_w
        w_rec = self.config.weight_recency / total_w
        w_clust = self.config.weight_cluster / total_w
        w_rep = self.config.weight_repeat / total_w

        reasons: List[str] = []
        limitations: List[str] = [
            "Satellite detection indicates a thermal anomaly, not confirmed ground-truth wildfire.",
            "Nearby cluster detections may not represent independent ignition sources.",
            "Review priority is a triage aid for human evaluators, not an emergency dispatch severity indicator."
        ]

        # Factor 1: Confidence
        s_conf = obs.confidence_normalized
        if s_conf >= 0.8:
            reasons.append(f"High satellite detection confidence ({s_conf * 100:.1f}%).")
        elif s_conf >= 0.5:
            reasons.append(f"Nominal satellite detection confidence ({s_conf * 100:.1f}%).")
        else:
            reasons.append(f"Low satellite detection confidence ({s_conf * 100:.1f}%). Subject to sensor noise or edge effects.")

        # Factor 2: Fire Radiative Power (FRP)
        if obs.frp is not None:
            # Saturation curve: 1 - exp(-FRP / ref_FRP)
            s_frp = 1.0 - math.exp(-obs.frp / max(1.0, self.config.frp_reference_mw))
            s_frp = max(0.0, min(1.0, s_frp))
            if obs.frp >= self.config.frp_reference_mw:
                reasons.append(f"Elevated Fire Radiative Power ({obs.frp:.1f} MW, >= reference {self.config.frp_reference_mw:.0f} MW).")
            elif obs.frp >= 10.0:
                reasons.append(f"Moderate Fire Radiative Power ({obs.frp:.1f} MW).")
            else:
                reasons.append(f"Low Fire Radiative Power ({obs.frp:.1f} MW).")
        else:
            # Explicitly handled missing feature: Neutral benchmark
            s_frp = 0.35
            limitations.append("FRP data was unavailable in source product for this observation; treated neutrally (0.35 score contribution).")

        # Factor 3: Recency
        obs_dt = datetime.strptime(obs.acq_datetime.replace("Z", ""), "%Y-%m-%dT%H:%M:%S")
        if dataset_max_time is None:
            dataset_max_time = obs_dt

        elapsed_hours = max(0.0, (dataset_max_time - obs_dt).total_seconds() / 3600.0)
        # Exponential decay over recency window
        s_rec = math.exp(-elapsed_hours / max(1.0, self.config.recency_window_hours))
        s_rec = max(0.0, min(1.0, s_rec))
        if elapsed_hours <= 12.0:
            reasons.append(f"Recent satellite observation ({elapsed_hours:.1f} hours from latest dataset record).")
        elif elapsed_hours <= 24.0:
            reasons.append(f"Observed within 24 hours ({elapsed_hours:.1f} hours elapsed).")
        else:
            reasons.append(f"Older detection ({elapsed_hours:.1f} hours elapsed relative to dataset reference).")

        # Factor 4: Spatial Cluster Size
        cluster_size = obs.cluster_size or 1
        s_clust = min(1.0, (cluster_size - 1) / 7.0) if cluster_size > 1 else 0.0
        if cluster_size > 3:
            reasons.append(f"Part of a multi-point spatial cluster ({cluster_size} co-located detections).")
        elif cluster_size > 1:
            reasons.append(f"Minor cluster grouping ({cluster_size} nearby points).")
        else:
            reasons.append("Isolated thermal detection (no nearby cluster formed).")

        # Factor 5: Repeat Detections
        rep_count = obs.repeat_detection_count or 0
        s_rep = min(1.0, rep_count / 5.0)
        if rep_count >= 3:
            reasons.append(f"Corroborated by {rep_count} nearby detections within the spatial window.")
        elif rep_count > 0:
            reasons.append(f"{rep_count} adjacent detection(s) found.")

        # Total Composite Score
        composite_score = (
            (w_conf * s_conf) +
            (w_frp * s_frp) +
            (w_rec * s_rec) +
            (w_clust * s_clust) +
            (w_rep * s_rep)
        )
        composite_score = round(max(0.0, min(1.0, composite_score)), 4)

        # Categorize
        if composite_score >= self.config.high_priority_threshold:
            level = "High Review Priority"
        elif composite_score >= self.config.medium_priority_threshold:
            level = "Medium Review Priority"
        else:
            level = "Low Review Priority"

        obs.priority_score = composite_score
        obs.priority_level = level
        obs.priority_reasons = reasons
        obs.priority_limitations = limitations
        return obs

    def rank_observations(
        self,
        observations: List[ObservationNormalized]
    ) -> List[ObservationNormalized]:
        """Rank a batch of observations and sort descending by priority score."""
        if not observations:
            return []

        # Find latest observation timestamp across the batch
        dts = [
            datetime.strptime(o.acq_datetime.replace("Z", ""), "%Y-%m-%dT%H:%M:%S")
            for o in observations
        ]
        max_dt = max(dts) if dts else datetime.utcnow()

        for obs in observations:
            self.calculate_observation_priority(obs, dataset_max_time=max_dt)

        # Sort descending by priority score
        return sorted(observations, key=lambda x: (x.priority_score or 0.0), reverse=True)
