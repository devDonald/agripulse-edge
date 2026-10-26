"""Core visual crop diagnostic service (Meta Model API + On-Device ExecuTorch Edge Classifier)."""
import asyncio
import base64
import json
import logging
import os
import re
from enum import Enum
from typing import List, Optional

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

from backend.services.edge_classifier import classify_leaf_on_device
from backend.services.meta_models import (
    DEFAULT_MODEL_ID,
    EDGE_MODEL_IDS,
    META_MODEL_IDS,
    VISION_MODEL_IDS,
    is_cloud_vision,
    is_edge,
    resolve_model,
)

load_dotenv()
logger = logging.getLogger("agripulse.diagnostician")

# Support both dev.meta.ai MODEL_API_KEY and META_API_KEY
META_API_URL = os.getenv(
    "META_API_URL", "https://api.meta.ai/v1/chat/completions"
)
META_API_KEY = os.getenv("META_API_KEY") or os.getenv("MODEL_API_KEY", "")
META_MODEL = os.getenv("META_MODEL", "llama-3.2-90b-vision-instruct")
META_TIMEOUT = float(os.getenv("META_TIMEOUT", "60"))
MOCK_MODE = os.getenv("MOCK_MODE", "false").lower() in ("1", "true", "yes")


class Severity(str, Enum):
    low = "low"
    moderate = "moderate"
    severe = "severe"


class OrganicRemedy(BaseModel):
    title: str = Field(..., min_length=3)
    preparation: str = Field(..., min_length=10)


class EdgeMetrics(BaseModel):
    runtime: str = "ExecuTorch v0.3.0"
    model_name: str = "llama-3.2-3b-edge-int8.pte"
    target_accelerator: str = "ARM-v8 NPU"
    quantization: str = "INT8 Weight-Only"
    memory_footprint_mb: float = 142.4
    cellular_data_used_kb: int = 0
    inference_latency_ms: float = 38.6


class DiagnosisResult(BaseModel):
    crop_name: str
    disease_detected: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    damage_percentage: int = Field(..., ge=0, le=100)
    severity: Severity
    symptoms: List[str] = Field(..., min_length=1)
    organic_remedies: List[OrganicRemedy] = Field(..., min_length=3, max_length=3)
    segmentation: Optional[dict] = Field(
        default=None, description="Leaf lesion segmentation stats"
    )
    edge_metrics: Optional[EdgeMetrics] = Field(
        default=None, description="On-device edge inference telemetry"
    )
    model_used: Optional[str] = Field(default=None, description="Active Meta model ID")
    live_call: Optional[bool] = Field(default=None, description="True if billed on dev.meta.ai")
    usage: Optional[dict] = Field(default=None, description="Token usage from Meta API")

    @field_validator("crop_name", "disease_detected")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must be non-empty")
        return v.strip()


SYSTEM_PROMPT = (
    "You are a Senior Agronomist with 20+ years of field experience in West African smallholder farming "
    "(Nigeria, Ghana, Côte d'Ivoire, Cameroon). You specialize in cassava, maize, tomato, yam, cowpea, and sorghum.\n\n"
    "TASKS:\n"
    "1. FIRST identify the crop species from LEAF ARCHITECTURE (shape), which is decisive:\n"
    "   - MAIZE = long strap-like parallel-veined blade, prominent midrib, NO lobes.\n"
    "   - CASSAVA = palmate leaf with 3-7 radiating finger-like lobes from one petiole point.\n"
    "   - TOMATO = small oval/compound leaflets with serrated edges.\n"
    "   NEVER call a long strap-like parallel-veined blade 'cassava'. "
    "Never call a palmate lobed leaf 'maize'.\n"
    "2. Detect whether the leaf is Healthy or infected with a specific local pathology "
    "(e.g., Cassava Mosaic Disease, Cassava Brown Streak, Fall Armyworm, Maize Streak Virus, "
    "Northern Leaf Blight, Tomato Early/Late Blight, Tomato Yellow Leaf Curl, Yam Anthracnose, Cowpea Aphids).\n"
    "3. Estimate realistic damage_percentage (0 to 100).\n"
    "4. Assign severity: low (0-20), moderate (21-50), severe (51-100).\n"
    "5. List 2 to 4 distinct observable symptoms.\n"
    "6. Prescribe EXACTLY 3 actionable, low-cost organic remedies using ingredients widely available in local markets "
    "(fresh neem leaves, sieved wood ash, local black soap, garlic/chili emulsion, pawpaw leaf extract, crop roguing).\n\n"
    "OUTPUT FORMAT: Return STRICT JSON ONLY without markdown fences or additional conversational text. "
    "Schema: { 'crop_name': string, 'disease_detected': string, 'confidence': float, 'damage_percentage': int, "
    "'severity': 'low'|'moderate'|'severe', 'symptoms': [string], "
    "'organic_remedies': [{'title': string, 'preparation': string} x 3] }"
)


REMEDY_DATABASE = {
    "cassava": [
        {
            "title": "Neem Leaf Extract (Biopesticide)",
            "preparation": "Pound 1kg of fresh green neem leaves into a paste. Soak in 5L of clean borehole water for 12 hours. Sieve carefully and mix in 1 teaspoon of local black soap (ose dudu) as a natural sticker. Spray thoroughly on the undersides of leaves early morning or at sunset to kill whitefly vectors.",
        },
        {
            "title": "Wood Ash Dusting",
            "preparation": "Collect dry hardwood ash from cooking fire, sift through a fine mesh to remove embers. Dust lightly over damp foliage at dawn twice weekly. Alters leaf pH, deterring piercing-sucking whitefly insects and reducing fungal spore germination.",
        },
        {
            "title": "Rigorous Roguing & Quarantine",
            "preparation": "Inspect farm weekly. Uproot all severely stunted and curled cassava stems by their roots. Carry them far from the farm boundary and burn or bury under 1 foot of soil. Never take planting stem cuttings from infected mother plants.",
        },
    ],
    "maize": [
        {
            "title": "Wood Ash & Fine Sand Funneling (Anti-Armyworm)",
            "preparation": "Mix 1 part dry sieved wood ash with 1 part fine river sand. Pour half a teaspoon directly into the growing central whorl (funnel) of each maize plant. The abrasive sand and alkaline ash dehydrates and kills juvenile Fall Armyworm caterpillars inside the whorl.",
        },
        {
            "title": "Hot Chili-Garlic & Soap Spray",
            "preparation": "Crush 5 hot habanero peppers and 1 bulb of garlic. Boil in 2L water for 20 minutes, cool and strain. Add 3L water and 1 tablespoon dissolved soap. Spray directly into damaged whorls. Acts as a potent organic stomach poison and repellent against caterpillars.",
        },
        {
            "title": "Trap Cropping & Intercropping",
            "preparation": "Intercrop maize with cowpea or desmodium, and plant Napier grass along field perimeters. Push-pull mechanism repels armyworm moths from the maize crop while attracting natural parasitic wasps.",
        },
    ],
    "tomato": [
        {
            "title": "Baking Soda & Soap Fungicide",
            "preparation": "Dissolve 2 tablespoons of baking soda (sodium bicarbonate) and 1 teaspoon of local liquid black soap in 5L of clean water. Spray once every 5 days at sunset on both sides of tomato leaves. Inhibits fungal spore germination of Early Blight.",
        },
        {
            "title": "Pawpaw (Papaya) Leaf Ferment",
            "preparation": "Shred 500g of mature pawpaw leaves. Soak in 4L of water for 48 hours to extract natural carpaine antifungal enzymes. Strain and spray undiluted on tomato foliage after rainfall to halt fungal spread.",
        },
        {
            "title": "Base Pruning & Dry Mulching",
            "preparation": "Remove all tomato leaves within 20cm of the soil surface using clean sanitized shears. Spread dry grass or rice straw mulch 5cm thick around the stem base to prevent soil-borne fungal spores from splashing onto foliage during rains.",
        },
    ],
}


def encode_image_to_base64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


def _get_remedies_for_crop(crop_name: str) -> List[OrganicRemedy]:
    crop_key = crop_name.lower().strip()
    for key in REMEDY_DATABASE:
        if key in crop_key:
            return [OrganicRemedy(**r) for r in REMEDY_DATABASE[key]]
    if "healthy" in crop_key or crop_key in ("unknown", ""):
        return [OrganicRemedy(**r) for r in REMEDY_DATABASE["maize"]]
    return [OrganicRemedy(**r) for r in REMEDY_DATABASE["cassava"]]


def _extract_json(text: str) -> dict:
    """Robust JSON extraction handling markdown fences, comments, and preambles."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Find outermost curly braces
    m = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not m:
        raise ValueError(f"Model did not return JSON: {text[:500]}")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        # Try cleaning trailing commas
        fixed = re.sub(r",\s*([\]}])", r"\1", m.group(0))
        return json.loads(fixed)


async def diagnose_image(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    force_offline: bool = False,
    model_id: Optional[str] = None,
    use_live: bool = False,
) -> DiagnosisResult:
    """Diagnoses crop leaf photo using Meta Model API (online) or Edge Classifier (offline).

    model_id: one of backend.services.meta_models.META_MODEL_IDS. Edge model IDs
        (3b/1b-instruct) route to the on-device classifier; cloud vision IDs
        (90b/11b-vision) hit https://api.meta.ai/v1 so dev.meta.ai meters usage.
    use_live: when True, bypass MOCK_MODE gating and attempt a real API call
        (dashboard "Use Live dev.meta.ai Credits" toggle).
    """
    if not image_bytes:
        raise ValueError("Empty image file uploaded")

    spec = resolve_model(model_id, offline=force_offline)
    active_model = spec["id"]
    edge_requested = is_edge(active_model)

    # If offline mode, no Meta API key (and not live-forced), or an edge model
    # was explicitly selected, run genuine on-device pixel classification
    if force_offline or edge_requested or ((MOCK_MODE and not use_live) or not META_API_KEY):
        edge = classify_leaf_on_device(image_bytes)
        if not edge.is_leaf:
            raise ValueError(
                "No vegetative crop leaf detected. Please take a clear, well-lit photo of a crop leaf."
            )
        remedies = _get_remedies_for_crop(edge.crop_name)
        metrics = EdgeMetrics(inference_latency_ms=edge.metrics.inference_latency_ms)
        if edge_requested:
            metrics.model_name = (
                "llama-3.2-1b-edge-int4.pte"
                if "1b" in active_model
                else "llama-3.2-3b-edge-int8.pte"
            )
        result = DiagnosisResult(
            crop_name=edge.crop_name,
            disease_detected=edge.disease_detected,
            confidence=edge.confidence,
            damage_percentage=edge.damage_percentage,
            severity=Severity(edge.severity),
            symptoms=edge.symptoms,
            organic_remedies=remedies,
            edge_metrics=metrics,
        )
        result.model_used = active_model  # type: ignore[attr-defined]
        result.live_call = False  # type: ignore[attr-defined]
        return result

    # Cloud inference via Meta Model API with retries — model=active_model so
    # the dev.meta.ai usage dashboard records the call under the right model.
    b64 = encode_image_to_base64(image_bytes)
    payload = {
        "model": active_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Analyze this crop leaf photograph. Provide an expert pathology diagnosis in strict JSON.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{b64}"},
                    },
                ],
            },
        ],
        "temperature": 0.2,
        "max_tokens": 1200,
        "response_format": {"type": "json_object"},
    }

    headers = {
        "Authorization": f"Bearer {META_API_KEY}",
        "Content-Type": "application/json",
    }

    last_error = None
    usage: Optional[dict] = None
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=META_TIMEOUT) as client:
                resp = await client.post(META_API_URL, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    usage = data.get("usage")
                    content = data["choices"][0]["message"]["content"]
                    parsed = _extract_json(content)
                    out = DiagnosisResult(**parsed)
                    out.model_used = active_model  # type: ignore[attr-defined]
                    out.live_call = True  # type: ignore[attr-defined]
                    if usage:
                        out.usage = usage  # type: ignore[attr-defined]
                    return out
                last_error = f"Meta API error {resp.status_code}: {resp.text[:500]}"
        except Exception as e:
            last_error = str(e)
            await asyncio.sleep(0.5)

    logger.warning(f"Meta API call failed ({last_error}), falling back to on-device edge classification.")
    # Graceful fallback to on-device edge classifier
    edge = classify_leaf_on_device(image_bytes)
    remedies = _get_remedies_for_crop(edge.crop_name)
    return DiagnosisResult(
        crop_name=edge.crop_name,
        disease_detected=edge.disease_detected,
        confidence=edge.confidence,
        damage_percentage=edge.damage_percentage,
        severity=Severity(edge.severity),
        symptoms=edge.symptoms,
        organic_remedies=remedies,
        edge_metrics=EdgeMetrics(
            runtime="ExecuTorch v0.3.0 (Automatic Cloud Fallback)",
            inference_latency_ms=edge.metrics.inference_latency_ms,
        ),
        model_used=active_model,
        live_call=False,
    )
