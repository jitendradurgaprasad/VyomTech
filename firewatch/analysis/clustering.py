"""
Spatial clustering module for active fire observations using DBSCAN with Haversine distance.
"""

from __future__ import annotations
import math
from typing import List, Tuple, Dict
import numpy as np
from sklearn.cluster import DBSCAN
from firewatch.config import ClusteringConfig
from firewatch.data.schemas import ObservationNormalized

EARTH_RADIUS_KM = 6371.0088


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points on Earth in kilometers."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_KM * c


class SpatialClusterer:
    """Groups nearby fire detections into spatial clusters without modifying raw records."""

    def __init__(self, config: ClusteringConfig):
        self.config = config

    def cluster_observations(
        self,
        observations: List[ObservationNormalized]
    ) -> List[ObservationNormalized]:
        """
        Apply DBSCAN using Haversine distance.
        Updates cluster_id, cluster_size, and repeat_detection_count on each observation in-place.
        """
        if not observations:
            return observations

        if not self.config.enabled or len(observations) < self.config.min_samples:
            for obs in observations:
                obs.cluster_id = -1
                obs.cluster_size = 1
                obs.repeat_detection_count = 0
            return observations

        # Extract coordinates in radians for Haversine metric
        coords = np.array([
            [math.radians(obs.latitude), math.radians(obs.longitude)]
            for obs in observations
        ])

        # Convert epsilon in km to radians
        eps_radians = self.config.eps_km / EARTH_RADIUS_KM

        db = DBSCAN(
            eps=eps_radians,
            min_samples=self.config.min_samples,
            metric="haversine"
        )
        labels = db.fit_predict(coords)

        # Count cluster sizes
        unique_labels, counts = np.unique(labels, return_counts=True)
        size_map = {lbl: cnt for lbl, cnt in zip(unique_labels, counts) if lbl != -1}

        # Calculate repeat detections (nearby observations within eps_km)
        for i, obs in enumerate(observations):
            label = int(labels[i])
            obs.cluster_id = label
            if label != -1:
                obs.cluster_size = int(size_map.get(label, 1))
                obs.repeat_detection_count = obs.cluster_size - 1
            else:
                obs.cluster_size = 1
                obs.repeat_detection_count = 0

        return observations

    @staticmethod
    def get_cluster_summaries(observations: List[ObservationNormalized]) -> List[Dict]:
        """Generate high-level summary for each detected cluster."""
        clusters: Dict[int, List[ObservationNormalized]] = {}
        for obs in observations:
            if obs.cluster_id is not None and obs.cluster_id >= 0:
                clusters.setdefault(obs.cluster_id, []).append(obs)

        summaries = []
        for cid, items in clusters.items():
            lats = [o.latitude for o in items]
            lons = [o.longitude for o in items]
            frps = [o.frp for o in items if o.frp is not None]
            max_frp = max(frps) if frps else None
            mean_frp = round(float(np.mean(frps)), 2) if frps else None
            
            summaries.append({
                "cluster_id": cid,
                "observation_count": len(items),
                "centroid_latitude": round(float(np.mean(lats)), 5),
                "centroid_longitude": round(float(np.mean(lons)), 5),
                "max_frp": max_frp,
                "mean_frp": mean_frp,
                "first_seen": min(o.acq_datetime for o in items),
                "last_seen": max(o.acq_datetime for o in items),
                "satellites": list(set(o.satellite for o in items))
            })
        
        return sorted(summaries, key=lambda x: x["observation_count"], reverse=True)
