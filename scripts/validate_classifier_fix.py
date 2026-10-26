"""Validate shape-first classifier: all samples + yellow-shifted maize stress test."""
import io
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.edge_classifier import classify_leaf_on_device

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_data")

EXPECTED = {
    "cassava_mosaic.jpg": ("cassava", "mosaic"),
    "maize_fall_armyworm.jpg": ("maize", "armyworm"),
    "tomato_early_blight.jpg": ("tomato", "blight"),
    "healthy_leaf.jpg": (None, "healthy"),
}

fails = 0
for fname, (exp_crop, exp_dis) in EXPECTED.items():
    with open(os.path.join(BASE, fname), "rb") as f:
        c = classify_leaf_on_device(f.read())
    ok_crop = exp_crop is None or c.crop_name == exp_crop
    ok_dis = exp_dis in c.disease_detected.lower()
    status = "OK " if (ok_crop and ok_dis) else "FAIL"
    if status == "FAIL":
        fails += 1
    print(f"[{status}] {fname} -> {c.crop_name} | {c.disease_detected} | dmg={c.damage_percentage}")

# ADVERSARIAL 1: realistic chlorosis — yellow-shift LEAF PIXELS ONLY (background stays dark,
# as in real field photos). Must STAY maize (the reported bug was maize -> cassava).
img = Image.open(os.path.join(BASE, "maize_fall_armyworm.jpg")).convert("RGB")
a = np.asarray(img).astype(int)
leaf_px = (a[:, :, 1] > 40) & (a[:, :, 1] > a[:, :, 0] * 0.6)
a[leaf_px, 0] = np.clip(a[leaf_px, 0] + 90, 0, 255)
a[leaf_px, 1] = np.clip(a[leaf_px, 1] + 70, 0, 255)
buf = io.BytesIO()
Image.fromarray(a.astype("uint8")).save(buf, format="JPEG")
c = classify_leaf_on_device(buf.getvalue())
ok = c.crop_name == "maize"
print(f"[{'OK ' if ok else 'FAIL'}] CHLOROTIC MAIZE (leaf-only) -> {c.crop_name} | {c.disease_detected}")
if not ok:
    fails += 1

# ADVERSARIAL 2: full-frame wash (macro-crop corner) — must NOT say cassava
img2 = Image.open(os.path.join(BASE, "maize_fall_armyworm.jpg")).convert("RGB")
b = np.asarray(img2).astype(int)
b[:, :, 0] = np.clip(b[:, :, 0] + 60, 0, 255)
b[:, :, 1] = np.clip(b[:, :, 1] + 50, 0, 255)
buf2 = io.BytesIO()
Image.fromarray(b.astype("uint8")).save(buf2, format="JPEG")
c2 = classify_leaf_on_device(buf2.getvalue())
ok2 = c2.crop_name != "cassava"
print(f"[{'OK ' if ok2 else 'FAIL'}] FULL-FRAME WASH -> {c2.crop_name} | {c2.disease_detected} (must not be cassava)")
if not ok2:
    fails += 1

print("ALL PASS" if fails == 0 else f"{fails} FAILURES")
sys.exit(1 if fails else 0)
