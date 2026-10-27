"""Comprehensive robustness and integration test suite for AgriPulse Edge."""
import os
import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

SAMPLE_DIR = "sample_data"


def test_health_check():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["offline_edge_ready"] is True


def test_diagnose_cassava_mosaic():
    path = os.path.join(SAMPLE_DIR, "cassava_mosaic.jpg")
    with open(path, "rb") as f:
        res = client.post("/api/v1/diagnose", files={"file": ("leaf.jpg", f, "image/jpeg")})
    assert res.status_code == 200
    data = res.json()
    assert "cassava" in data["crop_name"].lower()
    assert "mosaic" in data["disease_detected"].lower()
    assert data["confidence"] > 0.70
    assert len(data["organic_remedies"]) == 3
    assert "segmentation" in data
    assert "mask_overlay_base64" in data["segmentation"]
    assert data["segmentation"]["damage_percentage"] > 0


def test_diagnose_maize_fall_armyworm():
    path = os.path.join(SAMPLE_DIR, "maize_fall_armyworm.jpg")
    with open(path, "rb") as f:
        res = client.post("/api/v1/diagnose", files={"file": ("leaf.jpg", f, "image/jpeg")})
    assert res.status_code == 200
    data = res.json()
    assert data["crop_name"].lower() == "maize"
    assert "armyworm" in data["disease_detected"].lower()
    assert len(data["symptoms"]) >= 2
    assert len(data["organic_remedies"]) == 3


def test_diagnose_user_maize_rust():
    """Regression: user's real rust-covered maize blade must stay maize (never cassava)."""
    path = os.path.join(SAMPLE_DIR, "user_maize_rust.jpg")
    with open(path, "rb") as f:
        res = client.post("/api/v1/diagnose", files={"file": ("leaf.jpg", f, "image/jpeg")})
    assert res.status_code == 200
    data = res.json()
    assert data["crop_name"].lower() == "maize", f"got {data['crop_name']}"
    assert "rust" in data["disease_detected"].lower(), data["disease_detected"]
    assert len(data["organic_remedies"]) == 3


def test_diagnose_tomato_early_blight():
    path = os.path.join(SAMPLE_DIR, "tomato_early_blight.jpg")
    with open(path, "rb") as f:
        res = client.post("/api/v1/diagnose", files={"file": ("leaf.jpg", f, "image/jpeg")})
    assert res.status_code == 200
    data = res.json()
    assert data["crop_name"].lower() == "tomato"
    assert "blight" in data["disease_detected"].lower()


def test_diagnose_healthy_leaf():
    path = os.path.join(SAMPLE_DIR, "healthy_leaf.jpg")
    with open(path, "rb") as f:
        res = client.post("/api/v1/diagnose", files={"file": ("leaf.jpg", f, "image/jpeg")})
    assert res.status_code == 200
    data = res.json()
    assert "healthy" in data["disease_detected"].lower()
    assert data["severity"] == "low"


def test_diagnose_edge_zero_data():
    """Verifies the dedicated zero-data offline edge endpoint."""
    path = os.path.join(SAMPLE_DIR, "cassava_mosaic.jpg")
    with open(path, "rb") as f:
        res = client.post("/api/v1/diagnose-edge", files={"file": ("leaf.jpg", f, "image/jpeg")})
    assert res.status_code == 200
    data = res.json()
    assert "edge_metrics" in data
    assert data["edge_metrics"]["cellular_data_used_kb"] == 0
    assert "ExecuTorch" in data["edge_metrics"]["runtime"]
    assert data["edge_metrics"]["inference_latency_ms"] < 200


def test_reject_non_leaf_image():
    """Ensures input validation rejects photos without plant matter."""
    path = os.path.join(SAMPLE_DIR, "non_leaf_sample.jpg")
    with open(path, "rb") as f:
        res = client.post("/api/v1/diagnose", files={"file": ("wall.jpg", f, "image/jpeg")})
    assert res.status_code == 400
    assert "No vegetative crop leaf detected" in res.json()["detail"]


def test_reject_unsupported_mime():
    res = client.post("/api/v1/diagnose", files={"file": ("doc.txt", b"plain text", "text/plain")})
    assert res.status_code == 415


def test_reject_empty_file():
    res = client.post("/api/v1/diagnose", files={"file": ("empty.jpg", b"", "image/jpeg")})
    assert res.status_code == 400


def test_segment_endpoint():
    path = os.path.join(SAMPLE_DIR, "cassava_mosaic.jpg")
    with open(path, "rb") as f:
        res = client.post("/api/v1/segment", files={"file": ("leaf.jpg", f, "image/jpeg")})
    assert res.status_code == 200
    data = res.json()
    assert data["leaf_area_pixels"] > 1000
    assert data["damage_percentage"] >= 0.0
    assert len(data["mask_overlay_base64"]) > 50


def test_multilingual_voice_advisory_pidgin():
    req = {
        "query": "My cassava leaf get yellow spots, wetin I fit do with neem?",
        "language": "pidgin",
        "diagnosis_context": {"crop_name": "cassava", "disease_detected": "Cassava Mosaic"},
    }
    res = client.post("/api/v1/voice-advisory", json=req)
    assert res.status_code == 200
    data = res.json()
    assert data["detected_language"] == "pidgin"
    assert len(data["step_by_step_instructions"]) >= 3
    assert any("neem" in s.lower() or "dogonyaro" in s.lower() for s in data["step_by_step_instructions"])


def test_multilingual_voice_advisory_hausa():
    req = {
        "query": "Yaya zan hada maganin ganyen neem?",
        "language": "hausa",
        "diagnosis_context": {"crop_name": "cassava", "disease_detected": "Cassava Mosaic"},
    }
    res = client.post("/api/v1/voice-advisory", json=req)
    assert res.status_code == 200
    data = res.json()
    assert data["detected_language"] == "hausa"
    assert "sannu" in data["spoken_reply"].lower() or "abokina" in data["spoken_reply"].lower()


def test_multilingual_voice_advisory_yoruba():
    req = {
        "query": "Bawo ni mo se le lo ewe neem?",
        "language": "yoruba",
        "diagnosis_context": {"crop_name": "cassava", "disease_detected": "Cassava Mosaic"},
    }
    res = client.post("/api/v1/voice-advisory", json=req)
    assert res.status_code == 200
    data = res.json()
    assert data["detected_language"] == "yoruba"


def test_whatsapp_webhook_verification():
    """Tests Meta Webhook challenge verification handshake."""
    params = {
        "hub.mode": "subscribe",
        "hub.challenge": "1158201236",
        "hub.verify_token": "agripulse_hackathon_verify_token",
    }
    res = client.get("/api/v1/whatsapp/webhook", params=params)
    assert res.status_code == 200
    assert res.text == "1158201236"


def test_whatsapp_webhook_invalid_token():
    params = {
        "hub.mode": "subscribe",
        "hub.challenge": "1158201236",
        "hub.verify_token": "wrong_token",
    }
    res = client.get("/api/v1/whatsapp/webhook", params=params)
    assert res.status_code == 403


def test_whatsapp_webhook_incoming_message():
    """Tests inbound message handling and automated response generation."""
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "100234123",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"display_phone_number": "2348012345678"},
                            "messages": [
                                {
                                    "from": "2348099887766",
                                    "id": "wamid.HBgLMjM0ODA5O...",
                                    "timestamp": "1730000000",
                                    "text": {"body": "My maize leaves dey dry, wetin I fit do?"},
                                    "type": "text",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
    res = client.post("/api/v1/whatsapp/webhook", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "replied"
    assert "AgriPulse" in data["reply"]


def test_voice_synthesize_endpoint():
    """Tests audible voice note audio stream generation."""
    req = {"text": "How body my friend! Make you prepare neem spray.", "language": "pidgin"}
    res = client.post("/api/v1/voice-synthesize", json=req)
    assert res.status_code == 200
    assert len(res.content) > 50


def test_edge_benchmark_endpoint():
    """Tests ExecuTorch edge telemetry endpoint."""
    res = client.get("/api/v1/edge/benchmark")
    assert res.status_code == 200
    data = res.json()
    assert "llama_3_2_1b" in data
    assert "llama_3_2_3b" in data
    assert "sam_2_tiny" in data
    assert data["llama_3_2_3b"]["cellular_data_consumed_bytes"] == 0
    assert data["llama_3_2_3b"]["peak_ram_mb"] > 0
