"""Verify /segment + /voice-advisory + diagnose-with-segmentation."""
import base64
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MOCK_MODE", "true")

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from backend.main import app
from backend.services.leaf_segmenter import SegmentationResult
from backend.services.multilingual_advisor import AdvisoryResponse

PIDGIN_Q = "My cassava leaf get yellow spots and small holes, wetin I fit do with neem leaves?"


def make_leaf(path: str) -> str:
    img = Image.new("RGB", (640, 480), (34, 139, 34))
    d = ImageDraw.Draw(img)
    d.ellipse([200, 100, 440, 380], fill=(60, 180, 60), outline=(20, 100, 20), width=6)
    for x, y in ((260, 200), (310, 250), (350, 210), (290, 300)):
        d.ellipse([x, y, x + 40, y + 40], fill=(190, 190, 60))
    d.ellipse([330, 280, 350, 300], fill=(60, 30, 10))
    img.save(path, "JPEG")
    return path


def main() -> int:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    img_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(base, "sample_leaf.jpg")
    if not os.path.exists(img_path):
        make_leaf(img_path)
    print(f"Image: {img_path}")
    client = TestClient(app)

    # 1) segmentation endpoint
    with open(img_path, "rb") as f:
        r1 = client.post("/api/v1/segment", files={"file": ("leaf.jpg", f, "image/jpeg")})
    print(f"[segment] {r1.status_code}")
    b1 = r1.json()
    assert r1.status_code == 200, b1
    seg = SegmentationResult(**b1)
    assert seg.leaf_area_pixels > 0 and seg.damage_percentage >= 0
    raw = base64.b64decode(seg.mask_overlay_base64)
    assert raw[:8] == b"\x89PNG\r\n\x1a\n", "mask must be PNG"
    Image.open(io.BytesIO(raw)).verify()
    print(f"[segment] OK leaf={seg.leaf_area_pixels} lesion={seg.lesion_area_pixels} dmg={seg.damage_percentage}%")

    # 2) voice advisory endpoint (Pidgin)
    payload = {"query": PIDGIN_Q, "language": "pidgin",
               "diagnosis_context": {"crop_name": "cassava", "disease_detected": "Cassava Mosaic Disease"}}
    r2 = client.post("/api/v1/voice-advisory", json=payload)
    print(f"[voice] {r2.status_code}")
    b2 = r2.json()
    assert r2.status_code == 200, b2
    adv = AdvisoryResponse(**b2)
    assert adv.detected_language == "pidgin", b2
    assert len(adv.step_by_step_instructions) >= 3
    assert len(adv.preventative_cultural_practices) >= 1
    assert len(adv.local_market_substitutes) >= 1
    print(f"[voice] OK lang={adv.detected_language}")
    print(f"spoken_reply: {adv.spoken_reply}")
    print(f"steps: {adv.step_by_step_instructions}")

    # 3) diagnose now includes segmentation
    with open(img_path, "rb") as f:
        r3 = client.post("/api/v1/diagnose", files={"file": ("leaf.jpg", f, "image/jpeg")})
    b3 = r3.json()
    assert r3.status_code == 200, b3
    assert "segmentation" in b3 and b3["segmentation"] is not None, b3.keys()
    SegmentationResult(**b3["segmentation"])
    print(f"[diagnose] OK with segmentation dmg={b3['segmentation']['damage_percentage']}%")
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
