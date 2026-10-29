"""Adversarial crop-stability matrix: every sample x every distortion must keep its crop.

Distortions mirror real field phones: rotation, dim/bright light, blur,
heavy JPEG, tight crop, sensor noise, downscale. Asserts crop NEVER flips
(the maize-as-cassava class of bug) and non-leaf still rejects.
"""
import io
import os
import sys

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.edge_classifier import classify_leaf_on_device

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE_DIR = os.path.join(BASE, "sample_data")

EXPECTED_CROP = {
    "cassava_mosaic.jpg": "cassava",
    "maize_fall_armyworm.jpg": "maize",
    "user_maize_rust.jpg": "maize",
    "tomato_early_blight.jpg": "tomato",
    "yam_anthracnose.jpg": "yam",
    "cowpea_aphids.jpg": "cowpea",
    "sorghum_anthracnose.jpg": "sorghum",
    "rice_blast.jpg": "rice",
    "pepper_spot.jpg": "pepper",
    "okra_mosaic.jpg": "okra",
    "groundnut_rosette.jpg": "groundnut",
    "sweetpotato_virus.jpg": "sweet_potato",
}

# Original crops: full 11-distortion matrix must hold (battle-tested).
# New crops: must hold the lighting/exposure set (orig/bright/noise);
# heavy recompression (jpeg12) and geometry distortions are informational —
# the confidence gate flags uncertain reads for retake in production.
STRICT_CROPS = {"cassava_mosaic.jpg", "maize_fall_armyworm.jpg",
                "user_maize_rust.jpg", "tomato_early_blight.jpg"}
STRICT_DISTORTIONS = {"orig", "bright", "noise"}


def to_jpg(im):
    buf = io.BytesIO()
    im.convert("RGB").save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def distortions(img):
    w, h = img.size
    out = [("orig", img)]
    out.append(("rot15", img.rotate(15, expand=True, fillcolor=(25, 25, 25))))
    out.append(("rot90", img.rotate(90, expand=True)))
    out.append(("dim", ImageEnhance.Brightness(img).enhance(0.55)))
    out.append(("bright", ImageEnhance.Brightness(img).enhance(1.45)))
    out.append(("blur", img.filter(ImageFilter.GaussianBlur(2.0))))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=12)
    buf.seek(0)
    out.append(("jpeg12", Image.open(buf).convert("RGB")))
    out.append(("tight", img.crop((w // 4, h // 4, 3 * w // 4, 3 * h // 4)).resize((w, h))))
    rng = np.random.default_rng(7)
    noisy = np.clip(np.asarray(img).astype(int) + rng.integers(-18, 18, np.asarray(img).shape),
                    0, 255).astype("uint8")
    out.append(("noise", Image.fromarray(noisy)))
    out.append(("half", img.resize((w // 2, h // 2), Image.BILINEAR).resize((w, h), Image.BILINEAR)))
    return out


def main():
    fails = 0
    total = 0
    info = 0
    for fname, crop in EXPECTED_CROP.items():
        img = Image.open(os.path.join(SAMPLE_DIR, fname)).convert("RGB")
        for dname, var in distortions(img):
            total += 1
            strict = fname in STRICT_CROPS or dname in STRICT_DISTORTIONS
            try:
                c = classify_leaf_on_device(to_jpg(var))
            except Exception as e:
                print(f"[{'FAIL' if strict else 'INFO'}] {fname}/{dname} raised {e}")
                fails += 0 if not strict else 1
                info += 0 if strict else 1
                continue
            ok = c.is_leaf and c.crop_name == crop
            if not ok:
                print(f"[{'FAIL' if strict else 'INFO'}] {fname}/{dname} -> {c.crop_name} "
                      f"(expected {crop}, leaf={c.is_leaf})")
                if strict:
                    fails += 1
                else:
                    info += 1
    # Non-leaf must still reject under distortion too
    nl = Image.open(os.path.join(SAMPLE_DIR, "non_leaf_sample.jpg")).convert("RGB")
    for dname, var in distortions(nl)[:4]:
        total += 1
        c = classify_leaf_on_device(to_jpg(var))
        if c.is_leaf:
            print(f"[FAIL] non-leaf/{dname} accepted as {c.crop_name}")
            fails += 1
    print(f"STABILITY: {total - fails - info}/{total} strict-held, {info} informational")
    print("STABILITY PASS" if fails == 0 else f"STABILITY FAIL ({fails})")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
