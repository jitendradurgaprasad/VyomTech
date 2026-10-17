"""
SQLite Database and Storage Layer for FireWatch AI.
"""

from __future__ import annotations
import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from firewatch.data.schemas import ObservationNormalized


AUTHORITY_FEEDBACK_OUTCOMES = (
    "Confirmed wildfire",
    "Authorized/prescribed burn",
    "Known non-fire thermal source",
    "False satellite anomaly",
    "Unresolved / unable to verify",
)
SITE_MEMORY_OUTCOMES = frozenset({
    "Authorized/prescribed burn",
    "Known non-fire thermal source",
    "False satellite anomaly",
})
SITE_MEMORY_DAYS = 30


def exact_site_key(latitude: float, longitude: float) -> str:
    """Key an exact reported coordinate, without a geographic suppression radius."""
    return f"{float(latitude):.6f},{float(longitude):.6f}"


class DatabaseManager:
    """Manages SQLite persistence for observations, reviews, authorities, and notifications."""

    def __init__(self, db_path: str = "firewatch.db"):
        self.db_path = db_path
        self.init_database()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def init_database(self) -> None:
        """Create tables and indexes if they do not exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Observations Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS observations (
                    id TEXT PRIMARY KEY,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    acq_date TEXT NOT NULL,
                    acq_time TEXT NOT NULL,
                    acq_datetime TEXT NOT NULL,
                    satellite TEXT NOT NULL,
                    instrument TEXT NOT NULL,
                    confidence_raw TEXT,
                    confidence_normalized REAL NOT NULL,
                    confidence_category TEXT NOT NULL,
                    brightness_kelvin REAL,
                    bright_secondary REAL,
                    frp REAL,
                    daynight TEXT,
                    scan REAL,
                    track REAL,
                    source_product TEXT,
                    priority_score REAL,
                    priority_level TEXT,
                    priority_reasons TEXT,
                    priority_limitations TEXT,
                    cluster_id INTEGER,
                    cluster_size INTEGER,
                    repeat_detection_count INTEGER,
                    jurisdiction TEXT,
                    administrative_region TEXT,
                    raw_data_json TEXT,
                    created_at TEXT
                )
            """)

            # Review / Feedback Table (Preserves audit history)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reviews (
                    id TEXT PRIMARY KEY,
                    observation_id TEXT NOT NULL,
                    reviewer_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    assessment_confidence TEXT NOT NULL,
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    is_correction INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (observation_id) REFERENCES observations(id)
                )
            """)

            # Authorities Directory Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS authorities (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    jurisdiction TEXT NOT NULL,
                    region TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    contact_details TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    last_verified TEXT NOT NULL,
                    is_test_data INTEGER NOT NULL DEFAULT 1
                )
            """)

            # Notification Audit Log Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notification_audit (
                    id TEXT PRIMARY KEY,
                    observation_id TEXT NOT NULL,
                    authority_id TEXT,
                    recipient TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    trigger_reason TEXT NOT NULL,
                    priority_score REAL,
                    created_at TEXT NOT NULL,
                    attempted_at TEXT,
                    status TEXT NOT NULL,
                    provider_response TEXT,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    error_details TEXT,
                    payload_summary TEXT,
                    FOREIGN KEY (observation_id) REFERENCES observations(id)
                )
            """)

            # Create Indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_obs_datetime ON observations(acq_datetime)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_obs_priority ON observations(priority_score)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_obs_cluster ON observations(cluster_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_reviews_obs ON reviews(observation_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_notif_obs ON notification_audit(observation_id)")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS authority_feedback (
                    id TEXT PRIMARY KEY,
                    observation_id TEXT NOT NULL,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    authority_name TEXT NOT NULL,
                    case_reference TEXT NOT NULL,
                    source_verified INTEGER NOT NULL DEFAULT 0,
                    outcome TEXT NOT NULL,
                    reviewer_id TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (observation_id) REFERENCES observations(id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS site_feedback_memory (
                    id TEXT PRIMARY KEY,
                    feedback_id TEXT NOT NULL UNIQUE,
                    observation_id TEXT NOT NULL,
                    coordinate_key TEXT NOT NULL,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    outcome TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    deactivated_at TEXT,
                    deactivated_by_feedback_id TEXT,
                    FOREIGN KEY (feedback_id) REFERENCES authority_feedback(id),
                    FOREIGN KEY (observation_id) REFERENCES observations(id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_site_memory_coordinate ON site_feedback_memory(coordinate_key, active, expires_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_authority_feedback_observation ON authority_feedback(observation_id, created_at)")
            feedback_columns = {row[1] for row in cursor.execute("PRAGMA table_info(authority_feedback)").fetchall()}
            if "source_verified" not in feedback_columns:
                cursor.execute("ALTER TABLE authority_feedback ADD COLUMN source_verified INTEGER NOT NULL DEFAULT 0")
            
            conn.commit()

        # Seed default test authorities if table is empty
        self.seed_test_authorities_if_empty()

    def seed_test_authorities_if_empty(self) -> None:
        """Seed sample authority directory clearly marked as TEST DATA."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as cnt FROM authorities")
            count = cursor.fetchone()["cnt"]
            if count == 0:
                now_str = datetime.utcnow().strftime("%Y-%m-%d")
                test_authorities = [
                    (
                        "auth_emergency_unit",
                        "Regional Emergency Fire Response Unit",
                        "Immediate Fire & Thermal Triage Jurisdiction",
                        "All Regions / Nearest Emergency Unit",
                        "email",
                        "mjdp8086@gmail.com",
                        1,
                        now_str,
                        1
                    ),
                    (
                        "auth_central_queue",
                        "Central Satellite Fire Review Desk (SIMULATION)",
                        "Central National Triage Queue / Jurisdiction unknown",
                        "National / Unassigned",
                        "simulation",
                        "internal-queue://triage-central@firewatch.sim",
                        1,
                        now_str,
                        1
                    ),
                    (
                        "auth_mh_forest",
                        "Maharashtra Forest & Fire Department (TEST RECORD)",
                        "Maharashtra State Forest & Emergency Division",
                        "Maharashtra State",
                        "simulation",
                        "simulated-desk://mh-forest-control@example.test",
                        1,
                        now_str,
                        1
                    ),
                    (
                        "auth_mp_disaster",
                        "Madhya Pradesh State Disaster Response (TEST RECORD)",
                        "Madhya Pradesh State Forest & Emergency Division",
                        "Madhya Pradesh State",
                        "simulation",
                        "simulated-desk://mp-disaster-response@example.test",
                        1,
                        now_str,
                        1
                    ),
                    (
                        "auth_ap_forest",
                        "Andhra Pradesh Forest Command (TEST RECORD)",
                        "Andhra Pradesh State Forest & Emergency Division",
                        "Andhra Pradesh State",
                        "simulation",
                        "simulated-desk://ap-forest-desk@example.test",
                        1,
                        now_str,
                        1
                    ),
                ]
                cursor.executemany("""
                    INSERT INTO authorities 
                    (id, name, jurisdiction, region, channel, contact_details, active, last_verified, is_test_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, test_authorities)
                conn.commit()

    def save_observations(self, observations: List[ObservationNormalized]) -> int:
        """Upsert observations into SQLite."""
        if not observations:
            return 0

        now_str = datetime.utcnow().isoformat() + "Z"
        with self.get_connection() as conn:
            cursor = conn.cursor()
            data = [
                (
                    o.id,
                    o.latitude,
                    o.longitude,
                    o.acq_date,
                    o.acq_time,
                    o.acq_datetime,
                    o.satellite,
                    o.instrument,
                    o.confidence_raw,
                    o.confidence_normalized,
                    o.confidence_category,
                    o.brightness_kelvin,
                    o.bright_secondary,
                    o.frp,
                    o.daynight,
                    o.scan,
                    o.track,
                    o.source_product,
                    o.priority_score,
                    o.priority_level,
                    json.dumps(o.priority_reasons or []),
                    json.dumps(o.priority_limitations or []),
                    o.cluster_id,
                    o.cluster_size,
                    o.repeat_detection_count,
                    o.jurisdiction,
                    o.administrative_region,
                    json.dumps(o.raw_data or {}),
                    now_str
                )
                for o in observations
            ]
            cursor.executemany("""
                INSERT OR REPLACE INTO observations (
                    id, latitude, longitude, acq_date, acq_time, acq_datetime,
                    satellite, instrument, confidence_raw, confidence_normalized,
                    confidence_category, brightness_kelvin, bright_secondary, frp,
                    daynight, scan, track, source_product, priority_score, priority_level,
                    priority_reasons, priority_limitations, cluster_id, cluster_size,
                    repeat_detection_count, jurisdiction, administrative_region,
                    raw_data_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, data)
            conn.commit()
            return len(data)

    def get_all_observations(self, limit: Optional[int] = None) -> List[ObservationNormalized]:
        """Fetch all stored observations."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM observations ORDER BY priority_score DESC"
            if limit:
                query += f" LIMIT {int(limit)}"
            cursor.execute(query)
            rows = cursor.fetchall()
            
            result = []
            for r in rows:
                result.append(
                    ObservationNormalized(
                        id=r["id"],
                        latitude=r["latitude"],
                        longitude=r["longitude"],
                        acq_date=r["acq_date"],
                        acq_time=r["acq_time"],
                        acq_datetime=r["acq_datetime"],
                        satellite=r["satellite"],
                        instrument=r["instrument"],
                        confidence_raw=r["confidence_raw"],
                        confidence_normalized=r["confidence_normalized"],
                        confidence_category=r["confidence_category"],
                        brightness_kelvin=r["brightness_kelvin"],
                        bright_secondary=r["bright_secondary"],
                        frp=r["frp"],
                        daynight=r["daynight"],
                        scan=r["scan"],
                        track=r["track"],
                        source_product=r["source_product"],
                        priority_score=r["priority_score"],
                        priority_level=r["priority_level"],
                        priority_reasons=json.loads(r["priority_reasons"]) if r["priority_reasons"] else [],
                        priority_limitations=json.loads(r["priority_limitations"]) if r["priority_limitations"] else [],
                        cluster_id=r["cluster_id"],
                        cluster_size=r["cluster_size"],
                        repeat_detection_count=r["repeat_detection_count"],
                        jurisdiction=r["jurisdiction"],
                        administrative_region=r["administrative_region"],
                        raw_data=json.loads(r["raw_data_json"]) if r["raw_data_json"] else {}
                    )
                )
            return result

    def get_recent_observations(self, limit: int = 20) -> List[ObservationNormalized]:
        """Fetch most recent observations sorted by priority_score descending."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM observations 
                ORDER BY priority_score DESC, acq_datetime DESC 
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            result = []
            for r in rows:
                result.append(
                    ObservationNormalized(
                        id=r["id"],
                        latitude=r["latitude"],
                        longitude=r["longitude"],
                        acq_date=r["acq_date"],
                        acq_time=r["acq_time"],
                        acq_datetime=r["acq_datetime"],
                        satellite=r["satellite"],
                        instrument=r["instrument"],
                        confidence_raw=r["confidence_raw"],
                        confidence_normalized=r["confidence_normalized"],
                        confidence_category=r["confidence_category"],
                        brightness_kelvin=r["brightness_kelvin"],
                        bright_secondary=r["bright_secondary"],
                        frp=r["frp"],
                        daynight=r["daynight"],
                        scan=r["scan"],
                        track=r["track"],
                        source_product=r["source_product"],
                        priority_score=r["priority_score"],
                        priority_level=r["priority_level"],
                        priority_reasons=json.loads(r["priority_reasons"]) if r["priority_reasons"] else [],
                        priority_limitations=json.loads(r["priority_limitations"]) if r["priority_limitations"] else [],
                        cluster_id=r["cluster_id"],
                        cluster_size=r["cluster_size"],
                        repeat_detection_count=r["repeat_detection_count"],
                        jurisdiction=r["jurisdiction"],
                        administrative_region=r["administrative_region"],
                        raw_data=json.loads(r["raw_data_json"]) if r["raw_data_json"] else {}
                    )
                )
            return result

    def get_observation_by_id(self, obs_id: str) -> Optional[ObservationNormalized]:
        """Fetch single observation by ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM observations WHERE id = ?", (obs_id,))
            r = cursor.fetchone()
            if not r:
                return None
            return ObservationNormalized(
                id=r["id"],
                latitude=r["latitude"],
                longitude=r["longitude"],
                acq_date=r["acq_date"],
                acq_time=r["acq_time"],
                acq_datetime=r["acq_datetime"],
                satellite=r["satellite"],
                instrument=r["instrument"],
                confidence_raw=r["confidence_raw"],
                confidence_normalized=r["confidence_normalized"],
                confidence_category=r["confidence_category"],
                brightness_kelvin=r["brightness_kelvin"],
                bright_secondary=r["bright_secondary"],
                frp=r["frp"],
                daynight=r["daynight"],
                scan=r["scan"],
                track=r["track"],
                source_product=r["source_product"],
                priority_score=r["priority_score"],
                priority_level=r["priority_level"],
                priority_reasons=json.loads(r["priority_reasons"]) if r["priority_reasons"] else [],
                priority_limitations=json.loads(r["priority_limitations"]) if r["priority_limitations"] else [],
                cluster_id=r["cluster_id"],
                cluster_size=r["cluster_size"],
                repeat_detection_count=r["repeat_detection_count"],
                jurisdiction=r["jurisdiction"],
                administrative_region=r["administrative_region"],
                raw_data=json.loads(r["raw_data_json"]) if r["raw_data_json"] else {}
            )

    # ------------------ REVIEWS & FEEDBACK ------------------

    def save_review(
        self,
        observation_id: str,
        reviewer_id: str,
        status: str,
        assessment_confidence: str,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Record reviewer feedback. Preserves full audit trail.
        If a prior review existed for this observation, marks this as a correction.
        """
        review_id = f"rev_{uuid.uuid4().hex[:12]}"
        created_at = datetime.utcnow().isoformat() + "Z"

        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Check if existing review exists for this observation
            cursor.execute("SELECT COUNT(*) as cnt FROM reviews WHERE observation_id = ?", (observation_id,))
            prior_count = cursor.fetchone()["cnt"]
            is_correction = 1 if prior_count > 0 else 0

            cursor.execute("""
                INSERT INTO reviews (
                    id, observation_id, reviewer_id, status, assessment_confidence, notes, created_at, is_correction
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                review_id, observation_id, reviewer_id, status, assessment_confidence, notes, created_at, is_correction
            ))
            conn.commit()

        return {
            "id": review_id,
            "observation_id": observation_id,
            "reviewer_id": reviewer_id,
            "status": status,
            "assessment_confidence": assessment_confidence,
            "notes": notes,
            "created_at": created_at,
            "is_correction": bool(is_correction)
        }

    def get_reviews_for_observation(self, observation_id: str) -> List[Dict[str, Any]]:
        """Get all feedback entries for a specific observation in chronological order."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM reviews WHERE observation_id = ? ORDER BY created_at DESC
            """, (observation_id,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_latest_review_map(self) -> Dict[str, Dict[str, Any]]:
        """Return a mapping of observation_id to latest review record."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT r1.* FROM reviews r1
                JOIN (
                    SELECT observation_id, MAX(created_at) as max_time
                    FROM reviews GROUP BY observation_id
                ) r2 ON r1.observation_id = r2.observation_id AND r1.created_at = r2.max_time
            """)
            rows = cursor.fetchall()
            return {r["observation_id"]: dict(r) for r in rows}

    def get_all_reviews(self) -> List[Dict[str, Any]]:
        """Get all feedback submissions across the entire system."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT r.*, o.latitude, o.longitude, o.satellite, o.priority_score, o.priority_level
                FROM reviews r
                LEFT JOIN observations o ON r.observation_id = o.id
                ORDER BY r.created_at DESC
            """)
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    # ------------------ AUTHORITY OUTCOMES & EXACT-SITE MEMORY ------------------

    def save_authority_feedback(
        self,
        *,
        observation_id: str,
        authority_name: str,
        case_reference: str,
        outcome: str,
        reviewer_id: str,
        confidence: str,
        authority_source_verified: bool = False,
        notes: Optional[str] = None,
        remember_exact_site: bool = False,
    ) -> Dict[str, Any]:
        """Append an authority outcome and optionally remember one exact coordinate.

        A repeat-notification memory is only allowed for high-confidence,
        case-referenced non-wildfire outcomes. It never hides observations and
        expires after SITE_MEMORY_DAYS. A confirmed wildfire clears active
        memory at the same six-decimal coordinate.
        """
        authority_name = authority_name.strip()
        case_reference = case_reference.strip()
        reviewer_id = reviewer_id.strip()
        confidence = confidence.strip().lower()
        if outcome not in AUTHORITY_FEEDBACK_OUTCOMES:
            raise ValueError("Choose a supported authority outcome.")
        if not authority_name or not case_reference or not reviewer_id:
            raise ValueError("Authority name, case/reference, and reviewer are required.")
        if confidence not in {"high", "medium", "low"}:
            raise ValueError("Confidence must be high, medium, or low.")
        if remember_exact_site and (
            outcome not in SITE_MEMORY_OUTCOMES or confidence != "high" or not authority_source_verified
        ):
            raise ValueError("Exact-site memory requires a verified authority source and a high-confidence non-wildfire outcome.")

        feedback_id = f"af_{uuid.uuid4().hex[:12]}"
        memory_id = f"site_{uuid.uuid4().hex[:12]}"
        created = datetime.utcnow()
        created_at = created.isoformat(timespec="seconds") + "Z"
        expires_at = (created.replace(microsecond=0) + timedelta(days=SITE_MEMORY_DAYS)).isoformat() + "Z"

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT latitude, longitude FROM observations WHERE id = ?", (observation_id,))
            observation_row = cursor.fetchone()
            if observation_row is None:
                raise ValueError("The selected observation no longer exists in the database.")
            latitude, longitude = float(observation_row["latitude"]), float(observation_row["longitude"])
            coordinate_key = exact_site_key(latitude, longitude)

            cursor.execute("""
                INSERT INTO authority_feedback (
                    id, observation_id, latitude, longitude, authority_name, case_reference,
                    source_verified, outcome, reviewer_id, confidence, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                feedback_id, observation_id, latitude, longitude, authority_name, case_reference,
                int(authority_source_verified), outcome, reviewer_id, confidence,
                notes.strip() if notes else None, created_at
            ))

            cleared = 0
            if outcome == "Confirmed wildfire" and confidence == "high" and authority_source_verified:
                cursor.execute("""
                    UPDATE site_feedback_memory
                    SET active = 0, deactivated_at = ?, deactivated_by_feedback_id = ?
                    WHERE coordinate_key = ? AND active = 1
                """, (created_at, feedback_id, coordinate_key))
                cleared = cursor.rowcount

            if remember_exact_site:
                cursor.execute("""
                    INSERT INTO site_feedback_memory (
                        id, feedback_id, observation_id, coordinate_key, latitude, longitude,
                        outcome, created_at, expires_at, active
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, (
                    memory_id, feedback_id, observation_id, coordinate_key, latitude, longitude,
                    outcome, created_at, expires_at
                ))
            conn.commit()

        return {
            "id": feedback_id,
            "observation_id": observation_id,
            "latitude": latitude,
            "longitude": longitude,
            "outcome": outcome,
            "memory_created": remember_exact_site,
            "memories_cleared": cleared,
            "expires_at": expires_at if remember_exact_site else None,
        }

    def get_active_site_memory(self, latitude: float, longitude: float) -> Optional[Dict[str, Any]]:
        """Return unexpired memory for the exact six-decimal coordinate only."""
        now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        with self.get_connection() as conn:
            row = conn.execute("""
                SELECT m.*, f.authority_name, f.case_reference, f.reviewer_id, f.confidence,
                       f.notes, f.created_at AS feedback_created_at
                FROM site_feedback_memory m
                JOIN authority_feedback f ON f.id = m.feedback_id
                WHERE m.coordinate_key = ? AND m.active = 1 AND m.expires_at > ?
                ORDER BY m.created_at DESC LIMIT 1
            """, (exact_site_key(latitude, longitude), now)).fetchone()
            return dict(row) if row else None

    def get_active_site_memories(self) -> List[Dict[str, Any]]:
        """List active, unexpired memories for review in the dashboard."""
        now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT m.*, f.authority_name, f.case_reference, f.reviewer_id,
                       f.confidence, f.notes
                FROM site_feedback_memory m
                JOIN authority_feedback f ON f.id = m.feedback_id
                WHERE m.active = 1 AND m.expires_at > ?
                ORDER BY m.created_at DESC
            """, (now,)).fetchall()
            return [dict(row) for row in rows]

    def get_all_authority_feedback(self) -> List[Dict[str, Any]]:
        """Return the append-only authority response audit history."""
        with self.get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM authority_feedback ORDER BY created_at DESC
            """).fetchall()
            return [dict(row) for row in rows]

    def was_recently_suppressed_by_site_memory(self, observation_id: str, window_minutes: int = 60) -> bool:
        """Avoid writing repeated audit rows for the same suppressed feed record."""
        with self.get_connection() as conn:
            row = conn.execute("""
                SELECT created_at FROM notification_audit
                WHERE observation_id = ? AND status = 'suppressed_by_authority_feedback'
                ORDER BY created_at DESC LIMIT 1
            """, (observation_id,)).fetchone()
        if not row:
            return False
        try:
            last_time = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return False
        return (datetime.utcnow() - last_time).total_seconds() < window_minutes * 60

    # ------------------ AUTHORITIES DIRECTORY ------------------

    def get_all_authorities(self) -> List[Dict[str, Any]]:
        """List all configured authorities."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM authorities ORDER BY region, name")
            return [dict(r) for r in cursor.fetchall()]

    def add_or_update_authority(
        self,
        auth_id: str,
        name: str,
        jurisdiction: str,
        region: str,
        channel: str,
        contact_details: str,
        active: bool = True,
        is_test_data: bool = True
    ) -> None:
        """Add or update an authority entry."""
        now_str = datetime.utcnow().strftime("%Y-%m-%d")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO authorities
                (id, name, jurisdiction, region, channel, contact_details, active, last_verified, is_test_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                auth_id, name, jurisdiction, region, channel, contact_details, int(active), now_str, int(is_test_data)
            ))
            conn.commit()

    # ------------------ NOTIFICATION AUDIT LOGS ------------------

    def log_notification(
        self,
        notif_id: str,
        observation_id: str,
        authority_id: Optional[str],
        recipient: str,
        channel: str,
        trigger_reason: str,
        priority_score: Optional[float],
        status: str,
        provider_response: Optional[str] = None,
        retry_count: int = 0,
        error_details: Optional[str] = None,
        payload_summary: Optional[Dict[str, Any]] = None
    ) -> None:
        """Record an attempted or completed notification in the persistent audit log."""
        created_at = datetime.utcnow().isoformat() + "Z"
        attempted_at = created_at
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO notification_audit (
                    id, observation_id, authority_id, recipient, channel, trigger_reason,
                    priority_score, created_at, attempted_at, status, provider_response,
                    retry_count, error_details, payload_summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                notif_id, observation_id, authority_id, recipient, channel, trigger_reason,
                priority_score, created_at, attempted_at, status, provider_response,
                retry_count, error_details, json.dumps(payload_summary or {})
            ))
            conn.commit()

    def get_notification_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch chronological notification audit records."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM notification_audit ORDER BY created_at DESC LIMIT ?
            """, (limit,))
            return [dict(r) for r in cursor.fetchall()]

    def is_recently_notified(self, observation_id: str, window_minutes: int = 60) -> bool:
        """Check if an observation was recently notified to prevent duplicates."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT created_at FROM notification_audit
                WHERE observation_id = ? AND status IN ('simulated', 'delivered', 'provider_accepted')
                ORDER BY created_at DESC LIMIT 1
            """, (observation_id,))
            row = cursor.fetchone()
            if not row:
                return False
            
            try:
                last_time = datetime.strptime(row["created_at"].replace("Z", ""), "%Y-%m-%dT%H:%M:%S.%f")
            except ValueError:
                last_time = datetime.strptime(row["created_at"].replace("Z", ""), "%Y-%m-%dT%H:%M:%S")
            
            elapsed = (datetime.utcnow() - last_time).total_seconds() / 60.0
            return elapsed < window_minutes
