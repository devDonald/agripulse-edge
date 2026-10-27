"""Verify mobile PWA view + mobile sync endpoints (offline queue -> batch sync -> history)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MOCK_MODE", "true")

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)
fails = 0


def check(name, cond, extra=""):
    global fails
    print(f"[{'OK ' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        fails += 1


# 1) PWA view compiles + talks to backend helpers
try:
    import py_compile
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    py_compile.compile(os.path.join(base, "frontend", "mobile_farmer.py"), doraise=True)
    check("mobile_farmer.py compiles", True)
except Exception as e:
    check("mobile_farmer.py compiles", False, str(e)[:200])

# 2) Diagnose-edge works (what the phone camera calls)
with open(os.path.join(base, "sample_data", "maize_fall_armyworm.jpg"), "rb") as f:
    r = client.post("/api/v1/diagnose-edge", files={"file": ("leaf.jpg", f, "image/jpeg")})
check("POST /api/v1/diagnose-edge 200 + maize", r.status_code == 200 and r.json().get("crop_name") == "maize",
      f"-> {r.json().get('crop_name')}/{r.json().get('disease_detected')}" if r.status_code == 200 else r.text[:200])
diag = r.json() if r.status_code == 200 else {}

# 3) Dialect voice pipeline (what the 🔊 button calls)
r = client.post("/api/v1/voice-advisory",
                json={"query": "My maize leaf get problem, wetin I fit do?",
                      "language": "pidgin",
                      "diagnosis_context": {"crop_name": diag.get("crop_name"),
                                            "disease_detected": diag.get("disease_detected")}})
check("POST /api/v1/voice-advisory pidgin", r.status_code == 200 and r.json().get("detected_language") == "pidgin")
spoken = r.json().get("spoken_reply", "") if r.status_code == 200 else ""
r = client.post("/api/v1/voice-synthesize", json={"text": spoken[:350] or "How body!", "language": "pidgin"})
check("POST /api/v1/voice-synthesize audio bytes", r.status_code == 200 and len(r.content) > 50,
      f"({len(r.content)} bytes)")

# 4) Offline queue sync: batch of 2 scans, then history + idempotent re-send
# Unique farmer per run: the SQLite store persists across runs by design.
import uuid as _uuid

_FARMER = f"test-farmer-{_uuid.uuid4().hex[:8]}"
batch = {"farmer_id": _FARMER, "scans": [
    {"client_scan_id": "local-aaa", "crop_name": "maize", "disease_detected": "Fall Armyworm",
     "damage_percentage": 9, "severity": "moderate", "language": "pidgin"},
    {"client_scan_id": "local-bbb", "crop_name": "cassava", "disease_detected": "Cassava Mosaic Disease",
     "damage_percentage": 45, "severity": "severe", "language": "pidgin"},
]}
r = client.post("/api/v1/mobile/sync-batch", json=batch)
check("POST /api/v1/mobile/sync-batch accepted=2", r.status_code == 200 and r.json().get("accepted") == 2,
      str(r.json().get("accepted")) if r.status_code == 200 else r.text[:200])
r = client.get("/api/v1/mobile/history", params={"farmer_id": _FARMER})
check("GET /api/v1/mobile/history count=2", r.status_code == 200 and r.json().get("count") == 2)
r = client.post("/api/v1/mobile/sync", json={"farmer_id": _FARMER, "crop_name": "tomato",
                                             "disease_detected": "Early Blight", "damage_percentage": 15,
                                             "severity": "moderate", "language": "yoruba",
                                             "client_scan_id": "local-ccc"})
check("POST /api/v1/mobile/sync single", r.status_code == 200 and "scan_id" in r.json())
r = client.get("/api/v1/mobile/history", params={"farmer_id": _FARMER, "limit": 5})
check("history count=3 after single", r.status_code == 200 and r.json().get("count") == 3)
# Idempotent re-send: same batch must not duplicate rows
r = client.post("/api/v1/mobile/sync-batch", json=batch)
r = client.get("/api/v1/mobile/history", params={"farmer_id": _FARMER, "limit": 5})
check("re-send idempotent (still 3)", r.status_code == 200 and r.json().get("count") == 3)

print("ALL PASS" if fails == 0 else f"{fails} FAILURES")
sys.exit(1 if fails else 0)
