"""Verify Tasks 1+3: /health mirrors MODEL_CATALOG; WhatsApp image payload works."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["MOCK_MODE"] = "true"

from fastapi.testclient import TestClient

from backend.main import app
from backend.services.meta_models import MODEL_CATALOG

c = TestClient(app)

h = c.get("/health").json()
expected = [m["label"] for m in MODEL_CATALOG]
assert h["models_integrated"] == expected, f"catalog mismatch: {h['models_integrated']}"
print("TASK1 OK: /health mirrors MODEL_CATALOG (6 labels)")

payload = {
    "object": "whatsapp_business_account",
    "entry": [{
        "changes": [{
            "value": {
                "messages": [{
                    "from": "+2348012345678",
                    "type": "image",
                    "image": {"id": "sample_leaf_01", "caption": "Doctor, look my crop"},
                }]
            }
        }]
    }],
}
r = c.post("/api/v1/whatsapp/webhook", json=payload).json()
assert r["status"] == "replied", r
print("TASK3 OK: WhatsApp image payload ->", r["reply"][:80])
print("VERIFY PASS")
