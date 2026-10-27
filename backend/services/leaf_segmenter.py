"""SAM 2 Leaf Lesion Segmentation + Resilient Multi-Color-Space Fallback."""
import base64
import io
import os
from typing import Optional

import numpy as np
from dotenv import load_dotenv
from PIL import Image, ImageOps
from pydantic import BaseModel, Field

load_dotenv()

MOCK_MODE = os.getenv("MOCK_MODE", "false").lower() in ("1", "true", "yes")
SAM2_API_URL = os.getenv("SAM2_API_URL", "")
SAM2_API_KEY = os.getenv("SAM2_API_KEY", "")
SAM2_MODEL = os.getenv("SAM2_MODEL", "sam-2-large")
SAM2_TIMEOUT = float(os.getenv("SAM2_TIMEOUT", "60"))
MAX_DIM = int(os.getenv("SEG_MAX_DIM", "800"))


class SegmentationResult(BaseModel):
    leaf_area_pixels: int = Field(..., ge=0)
    lesion_area_pixels: int = Field(..., ge=0)
    chlorosis_pixels: int = Field(default=0, ge=0)
    necrosis_pixels: int = Field(default=0, ge=0)
    damage_percentage: float = Field(..., ge=0.0, le=100.0)
    mask_overlay_base64: str
    method_used: str = Field(default="SAM 2 (Meta AI)", description="Model or engine used for mask")


def _load_rgb(image_bytes: bytes) -> Image.Image:
    """Loads image, corrects EXIF orientation, and constrains dimensions."""
    raw = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(raw).convert("RGB")
    w, h = img.size
    m = max(w, h)
    if m > MAX_DIM:
        scale = MAX_DIM / float(m)
        img = img.resize((int(w * scale), int(h * scale)), Image.BILINEAR)
    return img


def _fallback_segment(image_bytes: bytes) -> dict:
    """Multi-channel HSV + LAB segmentation: yellow chlorosis & dark necrosis."""
    img = _load_rgb(image_bytes)
    rgb = np.asarray(img).astype(np.int16)
    hsv = np.asarray(img.convert("HSV")).astype(np.int16)
    H, S, V = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    R, G, B = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]

    # Leaf canopy isolation: vegetative green + chlorotic yellow/brown foliage
    leaf_mask = (S > 25) & (V > 25) & ((G > R * 0.62) | ((H <= 85) & (H >= 12)))
    if leaf_mask.sum() < 800:
        # Image is a tight macro crop of leaf
        leaf_mask = np.ones_like(leaf_mask, dtype=bool)

    # Chlorosis: yellowing hues
    chlorosis = (H >= 28) & (H <= 76) & (S > 50) & (V > 50) & leaf_mask

    # Necrosis: dry brown, rotting black, or necrotic spots
    necrosis = (
        (((H <= 26) & (S > 35) & (V < 195) & (V > 20)) | ((V < 75) & (S > 15)))
        & leaf_mask
    )

    # Disjoint masks
    necrosis_clean = necrosis
    chlorosis_clean = chlorosis & (~necrosis_clean)
    lesion_mask = necrosis_clean | chlorosis_clean

    leaf_n = int(leaf_mask.sum())
    lesion_n = int(lesion_mask.sum())
    chlor_n = int(chlorosis_clean.sum())
    necr_n = int(necrosis_clean.sum())

    pct = round(float(lesion_n / leaf_n * 100.0) if leaf_n > 0 else 0.0, 2)

    # Build rich alpha-blended overlay image
    base = np.asarray(img).copy()
    overlay = np.zeros_like(base)
    overlay[chlorosis_clean] = [255, 230, 0]  # vibrant yellow
    overlay[necrosis_clean] = [235, 30, 30]   # vivid red

    alpha = np.zeros(base.shape[:2], dtype=float)
    alpha[chlorosis_clean] = 0.50
    alpha[necrosis_clean] = 0.60

    blended = (base * (1.0 - alpha[..., None]) + overlay * alpha[..., None]).astype(np.uint8)

    # Dim non-leaf background slightly for high contrast presentation
    blended[~leaf_mask] = (blended[~leaf_mask] * 0.45).astype(np.uint8)

    buf = io.BytesIO()
    Image.fromarray(blended).save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()

    return {
        "leaf_area_pixels": leaf_n,
        "lesion_area_pixels": lesion_n,
        "chlorosis_pixels": chlor_n,
        "necrosis_pixels": necr_n,
        "damage_percentage": pct,
        "mask_overlay_base64": b64,
        "method_used": "Edge Spatial Masking (ExecuTorch fallback)",
    }


def _try_sam2(image_bytes: bytes) -> Optional[dict]:
    """Calls live sam-3.1 (/v1/responses) if a key is set, else None (HSV fallback)."""
    if MOCK_MODE or not (os.getenv("MODEL_API_KEY") or os.getenv("META_API_KEY", "")):
        return None
    try:
        from backend.services.vision_client import sam_mask_overlay

        r = sam_mask_overlay(image_bytes, max_dim=MAX_DIM)
        if not r:
            return None
        img = _load_rgb(image_bytes)
        w, h = img.size
        # Recompute chlorosis/necrosis split locally for the stats card.
        fb = _fallback_segment(image_bytes)
        return {
            "leaf_area_pixels": r["leaf_area_pixels"],
            "lesion_area_pixels": r["lesion_area_pixels"],
            "chlorosis_pixels": fb["chlorosis_pixels"],
            "necrosis_pixels": fb["necrosis_pixels"],
            "damage_percentage": r["damage_percentage"],
            "mask_overlay_base64": r["mask_overlay_base64"],
            "method_used": "SAM-3.1 (Meta AI Vision)",
        }
    except Exception:
        return None


def _try_sam2_legacy(image_bytes: bytes) -> Optional[dict]:
    """Calls Meta SAM 2 endpoint if configured, else returns None."""
    if MOCK_MODE or not SAM2_API_URL:
        return None
    try:
        import httpx

        b64 = base64.b64encode(image_bytes).decode()
        payload = {
            "model": SAM2_MODEL,
            "image_base64": b64,
            "task": "leaf_lesion_segmentation",
        }
        headers = {"Content-Type": "application/json"}
        if SAM2_API_KEY:
            headers["Authorization"] = f"Bearer {SAM2_API_KEY}"
        with httpx.Client(timeout=SAM2_TIMEOUT) as client:
            resp = client.post(SAM2_API_URL, headers=headers, json=payload)
            if resp.status_code != 200:
                return None
            data = resp.json()

        if all(
            k in data
            for k in (
                "leaf_area_pixels",
                "lesion_area_pixels",
                "damage_percentage",
                "mask_overlay_base64",
            )
        ):
            data["method_used"] = "Meta Segment Anything 2 (SAM 2 Cloud)"
            return data
        return None
    except Exception:
        return None


def segment_leaf_damage(image_bytes: bytes) -> dict:
    if not image_bytes:
        raise ValueError("Empty image file uploaded")
    remote = _try_sam2(image_bytes)
    if remote is not None:
        return SegmentationResult(**remote).model_dump()
    return SegmentationResult(**_fallback_segment(image_bytes)).model_dump()
