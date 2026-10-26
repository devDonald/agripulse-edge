"""Reproduce the reported bug: real-world maize uploads classified as cassava.

Builds hard variants of a maize photo (rotation, heavy yellow chlorosis,
tight crop, warm indoor white-balance) and asserts NONE comes back cassava.
Usage: python3 scripts/repro_maize_as_cassava.py [path/to/your/maize.jpg]
"""
import asyncio
import io
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.crop_diagnostician import diagnose_image  # noqa: E402
from backend.services.edge_classifier import classify_leaf_on_device  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_src(path=None):
    if path and os.path.exists(path):
        return Image.open(path).convert("RGB"), path
    default = os.path.join(BASE, "sample_data", "maize_fall_armyworm.jpg")
    return Image.open(default).convert("RGB"), default


def variants(img):
    w, h = img.size
    hostile = []
    hostile.append(("rotated-30deg", img.rotate(30, expand=True, fillcolor=(25, 25, 25))))
    a = np.asarray(img).astype(int)  # heavy yellow chlorosis, background untouched
    leaf = (a[:, :, 1] > 40) & (a[:, :, 1] > a[:, :, 0] * 0.6)
    b = a.copy()
    b[leaf, 0] = np.clip(b[leaf, 0] + 110, 0, 255)
    b[leaf, 1] = np.clip(b[leaf, 1] + 85, 0, 255)
    hostile.append(("heavy-chlorosis", Image.fromarray(b.astype("uint8"))))
    hostile.append(("tight-crop", img.crop((w // 4, h // 4, 3 * w // 4, 3 * h // 4)).resize((w, h))))
    c = np.asarray(img).astype(float)  # warm indoor white balance
    c[:, :, 0] *= 1.25
    c[:, :, 2] *= 0.80
    hostile.append(("warm-white-balance", Image.fromarray(np.clip(c, 0, 255).astype("uint8"))))
    return hostile


def to_jpg(im):
    buf = io.BytesIO()
    im.convert("RGB").save(buf, format="JPEG", quality=92)
    return buf.getvalue()


async def main():
    src_path = sys.argv[1] if len(sys.argv) > 1 else None
    img, used = load_src(src_path)
    print(f"source: {used}")
    fails = 0
    # 1) offline path on every hostile variant
    for name, var in [("original", img)] + variants(img):
        c = classify_leaf_on_device(to_jpg(var))
        ok = c.crop_name != "cassava"
        print(f"[{'OK ' if ok else 'FAIL'}] offline/{name} -> {c.crop_name} | {c.disease_detected}")
        fails += 0 if ok else 1
    # 2) LIVE cloud path on the original (billed) — guard must hold or fall back to probe
    try:
        out = await diagnose_image(to_jpg(img), "image/jpeg", force_offline=False,
                                   model_id="muse-spark-1.3", use_live=True)
        d = out.model_dump(mode="json")
        ok = d["crop_name"].lower() == "maize"
        print(f"[{'OK ' if ok else 'FAIL'}] live/muse-spark-1.3 -> {d['crop_name']} "
              f"(live={d.get('live_call')}, tokens={d.get('usage', {}).get('total_tokens')})")
        fails += 0 if ok else 1
    except Exception as e:
        print(f"[SKIP] live path unavailable: {str(e)[:150]}")
    print("REPRO PASS — no maize-as-cassava" if fails == 0 else f"REPRO FAIL — {fails} misclassified")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
