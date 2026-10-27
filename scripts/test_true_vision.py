"""Live TRUE-VISION diagnosis: your rust photo -> muse-image-1.0 (sees pixels)."""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.crop_diagnostician import diagnose_image  # noqa: E402
from backend.services.leaf_segmenter import segment_leaf_damage  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


async def main() -> int:
    raw = open(os.path.join(BASE, "sample_data", "user_maize_rust.jpg"), "rb").read()
    out = await diagnose_image(raw, "image/jpeg", force_offline=False,
                               model_id="muse-image-1.0", use_live=True)
    d = out.model_dump(mode="json")
    print("crop:", d["crop_name"])
    print("disease:", d["disease_detected"])
    print("model_used:", d.get("model_used"))
    print("live_call:", d.get("live_call"))
    print("usage:", json.dumps(d.get("usage")))
    seg = segment_leaf_damage(raw)
    print("segment:", seg["method_used"], seg["damage_percentage"],
          "mask_len:", len(seg["mask_overlay_base64"]))
    assert d["crop_name"].lower() == "maize", d
    assert d.get("live_call") is True
    assert d.get("model_used") == "muse-image-1.0"
    print("TRUE-VISION E2E PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
