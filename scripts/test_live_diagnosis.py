"""Live end-to-end cloud diagnosis: cassava leaf -> muse-spark-1.3 (billed)."""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.crop_diagnostician import diagnose_image  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


async def main() -> int:
    with open(os.path.join(BASE, "sample_data", "cassava_mosaic.jpg"), "rb") as f:
        img = f.read()
    out = await diagnose_image(img, "image/jpeg", force_offline=False,
                               model_id="muse-spark-1.3", use_live=True)
    d = out.model_dump(mode="json")
    print("crop:", d["crop_name"])
    print("disease:", d["disease_detected"])
    print("model_used:", d.get("model_used"))
    print("live_call:", d.get("live_call"))
    print("usage:", json.dumps(d.get("usage")))
    print("symptoms:", d.get("symptoms"))
    assert d.get("live_call") is True, "expected a billed live call"
    assert d.get("model_used") == "muse-spark-1.3"
    assert d.get("usage", {}).get("total_tokens", 0) > 0, "expected billed tokens"
    print("LIVE E2E PASS — tokens billed on dev.meta.ai")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
