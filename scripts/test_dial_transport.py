"""Dial transport tests: photo -> voice note, text -> advisory, call fallback."""
import base64
import io
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


r = client.get("/api/v1/dial/status")
check("GET /api/v1/dial/status (simulated w/o key)", r.status_code == 200)

with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "sample_data", "maize_fall_armyworm.jpg"), "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode()

r = client.post("/api/v1/dial/webhook", json={
    "type": "message.received",
    "message": {"from": "+2348012345678", "language": "pidgin",
                "body": "My maize leaf get holes, wetin I fit do?",
                "media": [{"content_type": "image/jpeg", "content_base64": img_b64}]},
})
d = r.json() if r.status_code == 200 else {}
check("Dial photo -> voice-note diagnosis", r.status_code == 200 and d.get("status") == "replied"
      and d.get("type") == "dial_image_diagnosis" and d.get("crop") == "maize"
      and d.get("voice_note_bytes", 0) > 50,
      f"crop={d.get('crop')} disease={d.get('disease')} bytes={d.get('voice_note_bytes')}")

r = client.post("/api/v1/dial/webhook", json={
    "type": "message.received",
    "message": {"from": "+2348012345678", "body": "How I go prepare neem spray?", "language": "hausa"},
})
d = r.json() if r.status_code == 200 else {}
check("Dial text -> Hausa advisory + voice", r.status_code == 200 and d.get("status") == "replied"
      and d.get("language") == "hausa", str(d.get("language")))

r = client.post("/api/v1/dial/webhook", json={"type": "message.received", "message": {}})
check("Dial empty event ignored", r.status_code == 200 and r.json().get("status") == "ignored")

r = client.post("/api/v1/dial/call", json={
    "to": "+2348012345678", "crop_name": "maize",
    "disease_detected": "Fall Armyworm", "damage_percentage": 9,
    "steps": ["Pour ash-sand mix inside the funnel.", "Spray neem at sunset."],
    "language": "pidgin"})
check("Dial outbound treatment call (simulated)", r.status_code == 200
      and r.json().get("simulated") is True)

print("ALL PASS" if fails == 0 else f"{fails} FAILURES")
sys.exit(1 if fails else 0)
