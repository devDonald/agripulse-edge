"""Verify WhatsApp image path: real bytes -> real diagnosis (no canned reply)."""
import base64
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


def wa_image_payload(b64=None, media_id="sample_leaf_01"):
    img = {"id": media_id, "caption": "Doctor, look my crop"}
    if b64:
        img["content_base64"] = b64
    return {"object": "whatsapp_business_account", "entry": [{
        "changes": [{"value": {"messages": [
            {"from": "+2348012345678", "type": "image", "image": img}]}}]}]}


with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "sample_data", "maize_fall_armyworm.jpg"), "rb") as f:
    leaf_b64 = base64.b64encode(f.read()).decode()

r = client.post("/api/v1/whatsapp/webhook", json=wa_image_payload(leaf_b64))
d = r.json() if r.status_code == 200 else {}
check("WA photo w/ bytes -> real maize diagnosis",
      r.status_code == 200 and d.get("type") == "image_diagnosis"
      and d.get("crop") == "maize" and "armyworm" in d.get("disease", "").lower()
      and "88%" not in d.get("reply", "") and "2.4%" not in d.get("reply", ""),
      f"crop={d.get('crop')} disease={d.get('disease')}")

r = client.post("/api/v1/whatsapp/webhook", json=wa_image_payload(None))
d = r.json() if r.status_code == 200 else {}
check("WA photo w/o bytes + no token -> honest unavailable (never fake cassava)",
      r.status_code == 200 and d.get("type") == "image_unavailable"
      and "Cassava" not in d.get("reply", ""),
      d.get("type"))

print("ALL PASS" if fails == 0 else f"{fails} FAILURES")
sys.exit(1 if fails else 0)
