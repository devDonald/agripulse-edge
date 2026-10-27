"""AgriPulse Edge: offline-first mobile sync store (SQLite, survives restarts)."""
import os
import sqlite3
import threading
import time
import uuid
from typing import Dict, List, Optional

_DB_PATH = os.getenv("SYNC_DB_PATH", os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "agripulse_sync.db",
))
_lock = threading.Lock()


def _conn():
    os.makedirs(os.path.dirname(os.path.abspath(_DB_PATH)), exist_ok=True)
    cx = sqlite3.connect(_DB_PATH, check_same_thread=False)
    cx.execute(
        """CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id TEXT UNIQUE, client_scan_id TEXT, farmer_id TEXT,
            crop_name TEXT, disease_detected TEXT, damage_percentage REAL,
            severity TEXT, language TEXT, latitude REAL, longitude REAL,
            timestamp TEXT, synced_at TEXT
        )"""
    )
    cx.execute("CREATE INDEX IF NOT EXISTS idx_farmer ON scans(farmer_id)")
    cx.commit()
    return cx


def save_scan(
    farmer_id: str,
    crop_name: str = "unknown",
    disease_detected: str = "unknown",
    damage_percentage: float = 0.0,
    severity: str = "low",
    language: str = "pidgin",
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    client_scan_id: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> dict:
    farmer_id = (farmer_id or "anonymous").strip() or "anonymous"
    record = {
        "scan_id": f"srv-{uuid.uuid4().hex[:8]}",
        "client_scan_id": client_scan_id or f"local-{uuid.uuid4().hex[:8]}",
        "farmer_id": farmer_id,
        "crop_name": crop_name,
        "disease_detected": disease_detected,
        "damage_percentage": damage_percentage,
        "severity": severity,
        "language": language,
        "latitude": latitude,
        "longitude": longitude,
        "timestamp": timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "synced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with _lock:
        cx = _conn()
        try:
            # Idempotent: same client_scan_id from the same farmer never duplicates.
            row = cx.execute(
                "SELECT scan_id FROM scans WHERE farmer_id=? AND client_scan_id=?",
                (farmer_id, record["client_scan_id"]),
            ).fetchone()
            if row:
                record["scan_id"] = row[0]
                return record
            cx.execute(
                "INSERT INTO scans (scan_id, client_scan_id, farmer_id, crop_name, disease_detected,"
                " damage_percentage, severity, language, latitude, longitude, timestamp, synced_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                tuple(record[k] for k in ("scan_id", "client_scan_id", "farmer_id", "crop_name",
                                          "disease_detected", "damage_percentage", "severity",
                                          "language", "latitude", "longitude", "timestamp", "synced_at")),
            )
            cx.commit()
        finally:
            cx.close()
    return record


def sync_batch(farmer_id: str, scans: List[dict]) -> dict:
    saved = []
    for s in scans or []:
        saved.append(
            save_scan(
                farmer_id=farmer_id,
                crop_name=str(s.get("crop_name", "unknown")),
                disease_detected=str(s.get("disease_detected", "unknown")),
                damage_percentage=float(s.get("damage_percentage", 0) or 0),
                severity=str(s.get("severity", "low")),
                language=str(s.get("language", "pidgin")),
                latitude=s.get("latitude"),
                longitude=s.get("longitude"),
                client_scan_id=s.get("client_scan_id"),
                timestamp=s.get("timestamp"),
            )
        )
    with _lock:
        cx = _conn()
        try:
            total = cx.execute(
                "SELECT COUNT(*) FROM scans WHERE farmer_id=?", ((farmer_id or "anonymous"),)
            ).fetchone()[0]
        finally:
            cx.close()
    return {
        "farmer_id": (farmer_id or "anonymous"),
        "accepted": len(saved),
        "total_stored": total,
        "scans": saved,
    }


def get_history(farmer_id: str, limit: int = 20) -> dict:
    farmer_id = (farmer_id or "anonymous").strip() or "anonymous"
    limit = max(1, min(limit, 100))
    with _lock:
        cx = _conn()
        try:
            rows = cx.execute(
                "SELECT scan_id, client_scan_id, farmer_id, crop_name, disease_detected,"
                " damage_percentage, severity, language, latitude, longitude, timestamp, synced_at"
                " FROM scans WHERE farmer_id=? ORDER BY id DESC LIMIT ?",
                (farmer_id, limit),
            ).fetchall()
            cols = [d[0] for d in cx.execute("SELECT * FROM scans LIMIT 0").description]
        finally:
            cx.close()
    items = [dict(zip(cols, r)) for r in rows]
    return {"farmer_id": farmer_id, "count": len(items), "scans": items}


# Back-compat shim for anything importing the old in-memory store.
SYNC_STORE: Dict[str, list] = {}

