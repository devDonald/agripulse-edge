"""Verify POST /api/v1/diagnose. Generates a sample leaf image if none given."""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MOCK_MODE", "true")

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from backend.main import app
from backend.services.crop_diagnostician import DiagnosisResult

REQUIRED = ["crop_name", "disease_detected", "confidence", "damage_percentage",
            "severity", "symptoms", "organic_remedies"]


def make_sample(path: str) -> str:
    img = Image.new("RGB", (640, 480), (34, 139, 34))
    d = ImageDraw.Draw(img)
    d.ellipse([200, 100, 440, 380], fill=(60, 180, 60), outline=(20, 100, 20), width=6)
    d.line([320, 110, 320, 370], fill=(20, 90, 20), width=5)
    for x in (260, 290, 350, 380):
        d.ellipse([x, 200, x + 40, 240], fill=(190, 190, 60))
    img.save(path, "JPEG")
    print(f"Sample leaf image written to {path}")
    return path


def main() -> int:
    img_path = sys.argv[1] if len(sys.argv) > 1 else "sample_leaf.jpg"
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not os.path.isabs(img_path):
        img_path = os.path.join(base, img_path)
    if not os.path.exists(img_path):
        make_sample(img_path)
    client = TestClient(app)
    with open(img_path, "rb") as f:
        files = {"file": (os.path.basename(img_path), f, "image/jpeg")}
        resp = client.post("/api/v1/diagnose", files=files)
    print(f"Status: {resp.status_code}")
    try:
        body = resp.json()
    except Exception:
        print(resp.text[:1000])
        return 1
    import json as j
    print(j.dumps(body, indent=2))
    assert resp.status_code == 200, body
    for k in REQUIRED:
        assert k in body, f"missing field {k}"
    parsed = DiagnosisResult(**body)  # strict schema check
    assert len(parsed.organic_remedies) == 3
    assert parsed.severity.value in ("low", "moderate", "severe")
    print("OK: schema valid, 3 remedies, severity valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
