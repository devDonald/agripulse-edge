"""AgriPulse Edge: offline-first mobile sync store (in-memory)."""
import time
import uuid
from typing import Dict, List, Optional


SYNC_STORE: Dict[str, list] = {}  # farmer_id -> scans


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
    SYNC_STORE.setdefault(farmer_id, []).append(record)
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
    return {
        "farmer_id": (farmer_id or "anonymous"),
        "accepted": len(saved),
        "total_stored": len(SYNC_STORE.get((farmer_id or "anonymous"), [])),
        "scans": saved,
    }


def get_history(farmer_id: str, limit: int = 20) -> dict:
    farmer_id = (farmer_id or "anonymous").strip() or "anonymous"
    items = SYNC_STORE.get(farmer_id, [])[-max(1, min(limit, 100)):]
    return {"farmer_id": farmer_id, "count": len(items), "scans": list(reversed(items))}
