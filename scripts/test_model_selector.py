"""Verify live model selector plumbing: catalog + per-model diagnose routing + advisory."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MOCK_MODE", "true")

from fastapi.testclient import TestClient

from backend.main import app
from backend.services.meta_models import META_MODEL_IDS

c = TestClient(app)
fails = 0


def check(name, cond, extra=""):
    global fails
    print(f"[{'OK ' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        fails += 1


r = c.get("/api/v1/models")
ids = [m["id"] for m in r.json().get("models", [])] if r.status_code == 200 else []
check("GET /api/v1/models lists 5 Meta IDs", ids == META_MODEL_IDS, str(ids))

with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "sample_data", "maize_fall_armyworm.jpg"), "rb") as f:
    img = f.read()

for mid in ["muse-spark-1.3", "llama-3.2-3b-edge",
            "llama-3.2-1b-edge"]:
    rr = c.post("/api/v1/diagnose", files={"file": ("m.jpg", img, "image/jpeg")},
                params={"model_id": mid})
    d = rr.json() if rr.status_code == 200 else {}
    check(f"diagnose model_id={mid.split('/')[-1]}",
          rr.status_code == 200 and d.get("crop_name") == "maize" and d.get("model_used") == mid,
          f"crop={d.get('crop_name')} model_used={d.get('model_used')} live={d.get('live_call')}")

r2 = c.post("/api/v1/voice-advisory",
            json={"query": "How I go prepare neem spray?", "language": "pidgin",
                  "model_id": "muse-spark-1.2"})
check("advisory model_id=11b routes pidgin",
      r2.status_code == 200 and r2.json().get("detected_language") == "pidgin")

# ping script safety: refuses without key / in mock without --force
import subprocess
p = subprocess.run([sys.executable, "scripts/ping_meta_models.py"],
                   capture_output=True, text=True, cwd=os.path.dirname(
                       os.path.dirname(os.path.abspath(__file__))), env={**os.environ})
check("ping_meta_models refuses safely in MOCK_MODE", p.returncode == 2, p.stdout.strip()[:100])

print("ALL PASS" if fails == 0 else f"{fails} FAILURES")
sys.exit(1 if fails else 0)
