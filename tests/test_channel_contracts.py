"""Cross-channel contracts: the same crop evidence must mean the same thing everywhere."""
import base64
import hashlib
import hmac
import json
import os

from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)
SAMPLE_DIR = "sample_data"


def _image_payload(path: str, message_id: str, caption: str = "") -> dict:
    with open(path, "rb") as handle:
        encoded = base64.b64encode(handle.read()).decode()
    return {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {
        "messages": [{"from": "2348000000001", "id": message_id, "type": "image",
                      "image": {"id": "test-media", "caption": caption,
                                "content_base64": encoded}}]
    }}]}]}


def test_damage_and_severity_are_consistent():
    with open(os.path.join(SAMPLE_DIR, "cassava_mosaic.jpg"), "rb") as handle:
        response = client.post("/api/v1/diagnose-edge", files={"file": ("leaf.jpg", handle, "image/jpeg")})
    assert response.status_code == 200
    result = response.json()
    damage = result["damage_percentage"]
    expected = "low" if damage <= 20 else "moderate" if damage <= 50 else "severe"
    assert result["severity"] == expected


def test_whatsapp_image_matches_api_crop_and_severity():
    path = os.path.join(SAMPLE_DIR, "maize_fall_armyworm.jpg")
    with open(path, "rb") as handle:
        api = client.post("/api/v1/diagnose-edge", files={"file": ("leaf.jpg", handle, "image/jpeg")}).json()
    payload = _image_payload(path, "wamid.channel-contract-1", "Pidgin advice")
    response = client.post("/api/v1/whatsapp/webhook", json=payload)
    assert response.status_code == 200
    result = response.json()
    assert result["type"] == "image_diagnosis"
    assert result["crop"] == api["crop_name"]
    assert result["damage"] == api["damage_percentage"]
    assert result["voice_sent"] is True


def test_whatsapp_webhook_retry_is_idempotent():
    payload = _image_payload(
        os.path.join(SAMPLE_DIR, "healthy_leaf.jpg"), "wamid.duplicate-contract-1"
    )
    first = client.post("/api/v1/whatsapp/webhook", json=payload)
    second = client.post("/api/v1/whatsapp/webhook", json=payload)
    assert first.json()["status"] == "replied"
    assert second.json() == {"status": "ignored", "reason": "duplicate message",
                             "message_id": "wamid.duplicate-contract-1"}


def test_whatsapp_signature_is_enforced(monkeypatch):
    secret = "test-app-secret"
    monkeypatch.setenv("WHATSAPP_APP_SECRET", secret)
    payload = {"object": "whatsapp_business_account", "entry": []}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    bad = client.post("/api/v1/whatsapp/webhook", content=raw,
                      headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256=bad"})
    assert bad.status_code == 401
    signature = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    good = client.post("/api/v1/whatsapp/webhook", content=raw,
                       headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature})
    assert good.status_code == 200
