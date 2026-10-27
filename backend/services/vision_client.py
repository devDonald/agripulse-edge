"""AgriPulse Edge: live Meta vision client (/v1/responses).

Verified 2026-10-27 against dev.meta.ai on THIS key:
  - muse-image-1.0: sees the photo (input_image + input_text), returns
    pixel-grounded crop/disease verdicts. Billed per photo.
  - sam-3.1: segmentation-only; returns lesion <|box|> + <|mask|> RLE
    (images_processed=1, 0 text tokens). Decoded locally to PNG.
"""
import base64
import io
import json
import logging
import os
import re

import httpx
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("agripulse.vision")

RESPONSES_URL = os.getenv("META_RESPONSES_URL", "https://api.meta.ai/v1/responses")
VISION_API_KEY = os.getenv("MODEL_API_KEY") or os.getenv("META_API_KEY", "")
VISION_TIMEOUT = float(os.getenv("VISION_TIMEOUT", "180"))
VISION_MODEL = os.getenv("VISION_MODEL", "muse-image-1.0")
SAM_MODEL = os.getenv("SAM_MODEL", "sam-3.1")


def _data_url(image_bytes: bytes, mime: str = "image/jpeg") -> str:
    return f"data:{mime};base64," + base64.b64encode(image_bytes).decode()


def _responses_post(payload: dict) -> dict:
    headers = {"Authorization": f"Bearer {VISION_API_KEY}", "Content-Type": "application/json"}
    with httpx.Client(timeout=VISION_TIMEOUT) as client:
        resp = client.post(RESPONSES_URL, headers=headers, json=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"responses API {resp.status_code}: {resp.text[:500]}")
        return resp.json()


def _output_texts(data: dict) -> list:
    out = []
    for item in data.get("output", []) or []:
        t = item.get("type")
        if t == "message":
            for c in item.get("content", []) or []:
                if c.get("text"):
                    out.append((c.get("type", "text"), c["text"]))
        elif t == "reasoning":
            for s in item.get("summary", []) or []:
                if s.get("text"):
                    out.append(("reasoning", s["text"]))
    return out


def ask_muse_image(image_bytes: bytes, question: str, model: str = None,
                   budget: int = 8000) -> dict:
    """Sends the REAL photo to muse-image; returns verdict text + usage."""
    data = _responses_post({
        "model": model or VISION_MODEL,
        "max_output_tokens": budget,
        "input": [{"role": "user", "content": [
            {"type": "input_text", "text": question},
            {"type": "input_image", "image_url": _data_url(image_bytes)},
        ]}],
    })
    texts = _output_texts(data)
    return {"verdict": "\n".join(t for _, t in texts), "parts": texts,
            "usage": data.get("usage", {}), "model": model or VISION_MODEL}


def sam31_mask(image_bytes: bytes,
               prompt: str = "segment the diseased spots on this leaf",
               model: str = None) -> dict:
    """Returns sam-3.1's raw box + RLE mask string, image size, and usage."""
    data = _responses_post({
        "model": model or SAM_MODEL,
        "max_output_tokens": 8000,
        "input": [{"role": "user", "content": [
            {"type": "input_text", "text": prompt},
            {"type": "input_image", "image_url": _data_url(image_bytes)},
        ]}],
    })
    texts = _output_texts(data)
    blob = "\n".join(t for _, t in texts)
    box = re.search(r"<\|box;([^|]+)\|>", blob)
    mask = re.search(r"<\|mask;x=(\d+);y=(\d+);data=(.+?)\s*$", blob, re.DOTALL)
    if mask is None:  # fallback: legacy closed form
        mask = re.search(r"<\|mask;([^;]+);data=([^|]+)\|>", blob, re.DOTALL)
    return {"box": box.group(1) if box else "",
            "mask_meta": f"x={mask.group(1)},y={mask.group(2)}" if mask and mask.lastindex == 3 else (mask.group(1) if mask else ""),
            "mask_data": mask.group(3) if mask and mask.lastindex == 3 else (mask.group(2) if mask else ""),
            "usage": data.get("usage", {}), "model": model or SAM_MODEL}


def decode_sam_mask(mask_data: str, width: int, height: int):
    """Decodes sam-3.1's RLE payload to boolean (h, w) mask. None if undecodable.

    Observed wire: '<h>,<w>,~<body>' where body mixes base-94 run chars with
    literal segments. Strategy: extract the longest base-94-looking run
    substring as the RLE stream; expand alternating off/on.
    """
    try:
        import numpy as np

        payload = mask_data.strip()
        m = re.match(r"(\d+),(\d+),~(.*)$", payload, re.DOTALL)
        body = m.group(3) if m else payload
        # Keep printable runs (base-94 alphabet); drop stray delimiters.
        streams = re.findall(r"[ -~]{32,}", body)
        if not streams:
            return None
        runs = [max(0, ord(c) - 33) for c in max(streams, key=len)]
        total = width * height
        flat = np.zeros(total, dtype=bool)
        pos, on = 0, False
        for run in runs:
            nxt = min(total, pos + run)
            if on:
                flat[pos:nxt] = True
            pos = nxt
            on = not on
            if pos >= total:
                break
        frac = flat.sum() / float(total)
        if flat.sum() == 0 or frac > 0.95:
            return None
        return flat.reshape((height, width))
    except Exception as e:
        logger.warning(f"SAM mask decode failed: {e}")
        return None


def sam_mask_overlay(image_bytes: bytes, max_dim: int = 800):
    """sam-3.1 mask -> red overlay PNG + stats. None on any failure (fallback)."""
    try:
        import numpy as np
        from PIL import Image, ImageOps

        img = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")
        w, h = img.size
        m = max(w, h)
        if m > max_dim:
            s = max_dim / float(m)
            img = img.resize((int(w * s), int(h * s)), Image.BILINEAR)
            w, h = img.size
        small = img.copy()
        if max(w, h) > 512:
            s2 = 512.0 / max(w, h)
            small = img.resize((int(w * s2), int(h * s2)), Image.BILINEAR)
        buf = io.BytesIO()
        small.save(buf, format="JPEG", quality=88)
        r = sam31_mask(buf.getvalue())
        if not r["mask_data"]:
            return None
        sw, sh = small.size
        decoded = decode_sam_mask(r["mask_data"], sw, sh)
        if decoded is None:
            return None
        mask = np.asarray(Image.fromarray(decoded.astype("uint8") * 255).resize(
            (w, h), Image.NEAREST)) > 127
        base = np.asarray(img).copy()
        overlay = np.zeros_like(base)
        overlay[mask] = [235, 30, 30]
        alpha = np.zeros(base.shape[:2], dtype=float)
        alpha[mask] = 0.55
        blended = (base * (1 - alpha[..., None]) + overlay * alpha[..., None]).astype("uint8")
        out = io.BytesIO()
        Image.fromarray(blended).save(out, format="PNG")
        n = int(mask.sum())
        return {"leaf_area_pixels": w * h, "lesion_area_pixels": n,
                "damage_percentage": round(n / float(w * h) * 100.0, 2),
                "mask_overlay_base64": base64.b64encode(out.getvalue()).decode(),
                "usage": r["usage"]}
    except Exception as e:
        logger.warning(f"sam_mask_overlay failed: {e}")
        return None
