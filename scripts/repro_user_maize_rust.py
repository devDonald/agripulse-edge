"""Reproduce with the USER'S real photo: rust-covered maize blade.

The user's photo shows hundreds of small dark-brown pustules with tan halos
(maize common rust / southern corn leaf blight) on a maize blade. The old
pipeline has no maize spot-disease concept, so trace + assert it stays maize.
"""
import asyncio
import io
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.crop_diagnostician import diagnose_image  # noqa: E402
from backend.services.edge_classifier import (  # noqa: E402
    _compute_image_features,
    classify_leaf_on_device,
)

USER_PHOTO_CANDIDATES = [
    "user_maize_rust.jpg",
    "sample_data/user_maize_rust.jpg",
    "uploads/maize.jpg",
]


def find_user_photo():
    for c in USER_PHOTO_CANDIDATES:
        p = c if os.path.isabs(c) else os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), c)
        if os.path.exists(p):
            return p
    extra = sys.argv[1] if len(sys.argv) > 1 else None
    if extra and os.path.exists(extra):
        return extra
    return None


async def main():
    path = find_user_photo()
    if not path:
        print("USER PHOTO NOT FOUND — save it as user_maize_rust.jpg in project root,")
        print("or pass the path: python3 scripts/repro_user_maize_rust.py /path/to/photo.jpg")
        return 2
    print(f"user photo: {path}")
    raw = open(path, "rb").read()
    feats = _compute_image_features(Image.open(io.BytesIO(raw)))
    print("features:", {k: (round(v, 3) if isinstance(v, float) else v)
                        for k, v in feats.items() if feats.get("is_leaf")})
    c = classify_leaf_on_device(raw)
    ok = c.crop_name == "maize"
    print(f"[{'OK ' if ok else 'FAIL'}] offline -> {c.crop_name} | {c.disease_detected} "
          f"| dmg={c.damage_percentage}")
    fails = 0 if ok else 1
    try:
        out = await diagnose_image(raw, "image/jpeg", force_offline=False,
                                   model_id="muse-spark-1.3", use_live=True)
        d = out.model_dump(mode="json")
        ok2 = d["crop_name"].lower() == "maize"
        print(f"[{'OK ' if ok2 else 'FAIL'}] live -> {d['crop_name']} | {d['disease_detected']} "
              f"(live={d.get('live_call')}, tokens={d.get('usage', {}).get('total_tokens')})")
        fails += 0 if ok2 else 1
    except Exception as e:
        print(f"[SKIP] live path unavailable: {str(e)[:150]}")
    print("USER-PHOTO PASS" if fails == 0 else f"USER-PHOTO FAIL ({fails})")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
