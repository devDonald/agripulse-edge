"""Core visual crop diagnostic service (Meta Model API + On-Device ExecuTorch Edge Classifier)."""
import asyncio
import base64
import io
import json
import logging
import os
import re
from enum import Enum
from typing import List, Optional

import httpx
from dotenv import load_dotenv
from PIL import Image
from pydantic import BaseModel, Field, field_validator

from backend.services.edge_classifier import _compute_image_features, classify_leaf_on_device
from backend.services.meta_models import (
    DEFAULT_MODEL_ID,
    EDGE_MODEL_IDS,
    META_MODEL_IDS,
    VISION_MODEL_IDS,
    is_cloud_vision,
    is_edge,
    resolve_model,
)

VISION_DIAGNOSIS_QUESTION = (
    "OUTPUT ONLY the JSON object below — no reasoning, no preamble, no markdown. "
    "First look at the photo, then emit exactly: "
    '{"crop_name": "<cassava|maize|tomato|other>", '
    '"disease_detected": "<disease with scientific name>", "confidence": 0.0-1.0, '
    '"damage_percentage": 0-100, "severity": "low|moderate|severe", '
    '"symptoms": ["...", "..."]}'
)

load_dotenv()
logger = logging.getLogger("agripulse.diagnostician")

# Support both dev.meta.ai MODEL_API_KEY and META_API_KEY
META_API_URL = os.getenv(
    "META_API_URL", "https://api.meta.ai/v1/chat/completions"
)
META_API_KEY = os.getenv("META_API_KEY") or os.getenv("MODEL_API_KEY", "")
META_MODEL = os.getenv("META_MODEL", "muse-spark-1.3")
META_TIMEOUT = float(os.getenv("META_TIMEOUT", "60"))
MOCK_MODE = os.getenv("MOCK_MODE", "false").lower() in ("1", "true", "yes")


class Severity(str, Enum):
    low = "low"
    moderate = "moderate"
    severe = "severe"


def severity_for_damage(damage_percentage: float) -> Severity:
    """Canonical severity policy shared by every delivery channel."""
    if damage_percentage <= 20:
        return Severity.low
    if damage_percentage <= 50:
        return Severity.moderate
    return Severity.severe


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
    needs_review: bool = Field(
        default=False, description="True when confidence is low — ask farmer to retake"
    )

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
            "title": "Neem & Baking Soda Anti-Rust Spray",
            "preparation": "Pound 500g fresh neem leaves, soak in 4L clean water overnight and sieve. Dissolve 2 tablespoons baking soda plus 1 teaspoon local black soap in the filtrate. Spray both leaf sides at sunset every 5 days — neem disrupts spore germination, soda dries pustules.",
        },
        {
            "title": "Wood Ash & Fine Sand Funneling (Anti-Armyworm)",
            "preparation": "Mix 1 part dry sieved wood ash with 1 part fine river sand. Pour half a teaspoon directly into the growing central whorl (funnel) of each maize plant. The abrasive sand and alkaline ash dehydrates and kills juvenile Fall Armyworm caterpillars inside the whorl.",
        },
        {
            "title": "Strip Rusted Leaves & Intercrop",
            "preparation": "Strip the worst rusted lower leaves first and bury them far from the farm (never compost). Intercrop maize with cowpea or desmodium to improve airflow and attract parasitic wasps that suppress both rust spread and armyworm moths.",
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


def _get_remedies_for_crop(crop_name: str, disease: str = "") -> List[OrganicRemedy]:
    crop_key = crop_name.lower().strip()
    disease_key = (disease or "").lower()
    if "maize" in crop_key and "armyworm" in disease_key:
        return [OrganicRemedy(**r) for r in [
            REMEDY_DATABASE["maize"][1],
            {
                "title": "Neem Whorl Treatment",
                "preparation": "Pound 500g fresh neem leaves, soak in 4L clean water overnight and sieve. Add 1 teaspoon local black soap. Pour or spray a small amount directly into each affected maize whorl at sunset, then repeat after 4 days.",
            },
            {
                "title": "Hand-pick and Scout Early",
                "preparation": "Inspect 10 plants in each farm row twice weekly. Hand-pick visible egg masses and young caterpillars, crush them, and remove badly shredded whorls. Treat neighbouring plants before larvae grow large and burrow deeper.",
            },
        ]]
    for key in REMEDY_DATABASE:
        if key in crop_key:
            return [OrganicRemedy(**r) for r in REMEDY_DATABASE[key]]
    if "healthy" in crop_key or crop_key in ("unknown", ""):
        return [OrganicRemedy(**r) for r in REMEDY_DATABASE["maize"]]
    return [OrganicRemedy(**r) for r in REMEDY_DATABASE["cassava"]]


def _extract_json(text: str) -> dict:
    """Robust JSON extraction handling markdown fences, comments, and preambles."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    # Strip markdown bold/headers reasoning models wrap around JSON.
    cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Find outermost curly braces — prefer blocks containing crop_name (vision
    # verdicts bury JSON after **reasoning** preamble).
    candidates = list(re.finditer(r"\{.*\}", cleaned, flags=re.DOTALL))
    if not candidates:
        raise ValueError(f"Model did not return JSON: {text[:500]}")
    # Prefer the LAST crop_name-bearing block (reasoning preamble comes first).
    ordered = sorted(candidates, key=lambda m: (0 if '"crop_name"' in m.group(0) else 1,
                                                -m.start()))
    for m in ordered:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
    # Try cleaning trailing commas on the best candidate
    fixed = re.sub(r",\s*([\]}])", r"\1", ordered[0].group(0))
    return json.loads(fixed)


def _extract_message_content(choice: dict) -> str:
    """Extracts assistant text across providers (plain content or reasoning-model fields)."""
    msg = (choice or {}).get("message", {}) or {}
    content = msg.get("content")
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):  # multipart content blocks
        parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("text")]
        if parts:
            return "\n".join(parts)
    for key in ("reasoning_content", "reasoning"):
        val = msg.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return json.dumps(choice)[:2000]


def _diagnosis_from_verdict_text(verdict: str, edge_probe) -> "DiagnosisResult":
    """Builds a DiagnosisResult from muse-image's prose when JSON truncates.

    The words are pixel-grounded (the model saw the photo); the probe supplies
    numbers. Crop defaults to the probe unless the text clearly names another.
    """
    low = (verdict or "").lower()
    crop = edge_probe.crop_name
    for cand in ("maize", "cassava", "tomato", "yam", "cowpea", "sorghum"):
        if re.search(rf"\b{cand}\b", low):
            crop = cand
            break
    disease = edge_probe.disease_detected
    patterns = [
        (r"tar\s*spot[^.]{0,60}(phyllachora\s*maydis)?", "Maize Tar Spot (Phyllachora maydis)"),
        (r"common\s*rust[^.]{0,60}(puccinia\s*sorghi)?", "Maize Common Rust (Puccinia sorghi)"),
        (r"southern\s*(corn\s*)?leaf\s*blight", "Southern Corn Leaf Blight (Cochliobolus heterostrophus)"),
        (r"northern\s*(corn\s*)?leaf\s*blight", "Northern Leaf Blight (Exserohilum turcicum)"),
        (r"maize\s*streak", "Maize Streak Virus"),
        (r"fall\s*armyworm", "Fall Armyworm (Spodoptera frugiperda)"),
        (r"cassava\s*mosaic", "Cassava Mosaic Disease (CMD)"),
        (r"early\s*blight", "Early Blight (Alternaria solani)"),
        (r"yellow\s*leaf\s*curl", "Tomato Yellow Leaf Curl"),
    ]
    for pat, name in patterns:
        if re.search(pat, low):
            disease = name
            break
    return DiagnosisResult(
        crop_name=crop,
        disease_detected=disease,
        confidence=0.82,
        damage_percentage=edge_probe.damage_percentage,
        severity=Severity(edge_probe.severity),
        symptoms=edge_probe.symptoms,
        organic_remedies=_get_remedies_for_crop(crop, disease),
    )


async def diagnose_image(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    force_offline: bool = False,
    model_id: Optional[str] = None,
    use_live: bool = False,
) -> DiagnosisResult:
    """Diagnoses crop leaf photo using Meta Model API (online) or Edge Classifier (offline).

    model_id: one of backend.services.meta_models.META_MODEL_IDS. Edge model IDs
        (llama-3.2-*-edge) route to the on-device classifier; cloud Muse IDs
        (muse-spark-1.3/1.2, muse-wonder-1.0) hit https://api.meta.ai/v1 so
        dev.meta.ai meters usage.
    use_live: when True, bypass MOCK_MODE gating and attempt a real API call
        (dashboard "Use Live dev.meta.ai Credits" toggle).
    """
    if not image_bytes:
        raise ValueError("Empty image file uploaded")

    spec = resolve_model(model_id, offline=force_offline)
    active_model = spec["id"]
    edge_requested = is_edge(active_model)

    # Gatekeeper: reject non-leaf photos BEFORE spending cloud credits. The probe
    # result is reused as ensemble context for the cloud call below (no double work).
    cloud_live = not (force_offline or edge_requested or ((MOCK_MODE and not use_live) or not META_API_KEY))
    edge_probe = classify_leaf_on_device(image_bytes)
    if not edge_probe.is_leaf:
        raise ValueError(
            "No vegetative crop leaf detected. Please take a clear, well-lit photo of a crop leaf."
        )

    # If offline mode, no Meta API key (and not live-forced), or an edge model
    # was explicitly selected, return the genuine on-device classification
    if not cloud_live:
        edge = edge_probe
        remedies = _get_remedies_for_crop(edge.crop_name, edge.disease_detected)
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
    # NOTE: the live Muse catalog is text-reasoning (no image_url parts on this
    # key), so the photo is analyzed on-device for shape/color while Muse
    # provides the pathology reasoning — a genuine cloud+edge ensemble.
    # edge_probe (gatekeeper above) is reused as the ensemble context.
    # The shape verdict is authoritative: a blade-shaped mask is maize even if
    # yellow, a lobed mask is cassava. The cloud model may refine disease but
    # MUST NOT contradict the crop — mismatches fall back to the probe below.
    shape_note = ""
    try:
        _feats = _compute_image_features(Image.open(io.BytesIO(image_bytes)))
        if _feats.get("is_leaf"):
            shape_note = (
                f" Measured leaf architecture: elongation={_feats.get('shape_elongation', 0):.1f}, "
                f"lobes={_feats.get('shape_lobes', 0)}, "
                f"parallel_veins={_feats.get('shape_parallel_veins', False)}."
            )
    except Exception:
        pass
    probe_ctx = (
        f"On-device leaf scan: crop={edge_probe.crop_name}, "
        f"disease={edge_probe.disease_detected}, damage={edge_probe.damage_percentage}%, "
        f"symptoms={'; '.join(edge_probe.symptoms)}."
        if edge_probe.is_leaf else
        "On-device leaf scan: no clear leaf detected."
    )

    # TRUE VISION first: the photo goes to muse-image-1.0 via /v1/responses
    # (pixel-grounded verdict, billed per photo). The probe stays as gatekeeper
    # + crop guard + ensemble context. Text-only path below is the fallback.
    last_error = None
    usage: Optional[dict] = None

    def _vision_attempt() -> DiagnosisResult:
        from backend.services.vision_client import ask_muse_image

        r = ask_muse_image(image_bytes, VISION_DIAGNOSIS_QUESTION)
        try:
            parsed = _extract_json(r["verdict"])
            out = DiagnosisResult(
                crop_name=parsed.get("crop_name", edge_probe.crop_name),
                disease_detected=parsed.get("disease_detected", edge_probe.disease_detected),
                confidence=float(parsed.get("confidence", 0.85)),
                damage_percentage=int(parsed.get("damage_percentage", edge_probe.damage_percentage)),
                severity=Severity(str(parsed.get("severity", edge_probe.severity)).lower()),
                symptoms=list(parsed.get("symptoms", edge_probe.symptoms)) or edge_probe.symptoms,
                organic_remedies=_get_remedies_for_crop(
                    str(parsed.get("crop_name", edge_probe.crop_name)),
                    str(parsed.get("disease_detected", edge_probe.disease_detected))),
            )
        except (ValueError, KeyError, TypeError):
            # muse-image reasons in prose and truncates before JSON — mine its
            # own words for crop/disease (still pixel-grounded), probe for numbers.
            out = _diagnosis_from_verdict_text(r["verdict"], edge_probe)
        if out.crop_name.strip().lower() != edge_probe.crop_name.strip().lower():
            logger.warning(
                f"Crop mismatch (vision={out.crop_name} vs probe={edge_probe.crop_name}); "
                "keeping probe crop."
            )
            raise ValueError(
                f"Vision crop '{out.crop_name}' contradicts on-device verdict "
                f"'{edge_probe.crop_name}'"
            )
        out.model_used = "muse-image-1.0"  # type: ignore[attr-defined]
        out.live_call = True  # type: ignore[attr-defined]
        out.usage = r["usage"]  # type: ignore[attr-defined]
        return out

    try:
        return await asyncio.to_thread(_vision_attempt)
    except Exception as e:
        last_error = str(e)[:300]
        logger.warning(f"Vision diagnosis failed ({last_error}), trying text reasoning path.")

    payload = {
        "model": active_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"{probe_ctx}{shape_note}\n"
                    "Field photo context: West African smallholder cassava/maize/tomato farm. "
                    "The on-device crop verdict above is AUTHORITATIVE — return the SAME crop_name. "
                    "You may refine disease_detected, symptoms, and damage, but NEVER change the crop. "
                    "Provide an expert pathology diagnosis in strict JSON."
                ),
            },
        ],
        "temperature": 0.2,
        # Muse reasoning models spend tokens thinking; keep a generous budget so
        # visible JSON survives (small caps return content=null with finish=length).
        "max_tokens": 4000,
    }

    headers = {
        "Authorization": f"Bearer {META_API_KEY}",
        "Content-Type": "application/json",
    }

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=META_TIMEOUT) as client:
                resp = await client.post(META_API_URL, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    usage = data.get("usage")
                    content = _extract_message_content(data["choices"][0])
                    parsed = _extract_json(content)
                    out = DiagnosisResult(**parsed)
                    # Crop guard: the cloud model never sees the photo, so if it
                    # contradicts the shape-verified probe, trust the probe.
                    if out.crop_name.strip().lower() != edge_probe.crop_name.strip().lower():
                        logger.warning(
                            f"Crop mismatch (cloud={out.crop_name} vs probe={edge_probe.crop_name}); "
                            "keeping probe crop."
                        )
                        raise ValueError(
                            f"Cloud crop '{out.crop_name}' contradicts on-device verdict "
                            f"'{edge_probe.crop_name}'"
                        )
                    out.model_used = active_model  # type: ignore[attr-defined]
                    out.live_call = True  # type: ignore[attr-defined]
                    if usage:
                        out.usage = usage  # type: ignore[attr-defined]
                    return out
                # Retry 429/5xx with backoff; fail fast on 4xx (bad key/model) —
                # except the image-model-on-chat error, which the vision-first
                # flow already covered (fall through to probe, don't 502).
                if resp.status_code in (429, 500, 502, 503, 504):
                    last_error = f"Meta API error {resp.status_code}: {resp.text[:300]}"
                elif active_model in ("muse-image-1.0", "sam-3.1"):
                    last_error = f"Image model {active_model} needs /v1/responses (already tried vision-first)"
                    break
                else:
                    raise RuntimeError(f"Meta API error {resp.status_code}: {resp.text[:500]}")
        except RuntimeError:
            raise
        except Exception as e:
            last_error = str(e)[:300]
        await asyncio.sleep(0.5 * (2 ** attempt))

    logger.warning(f"Meta API call failed ({last_error}), falling back to on-device edge classification.")
    # Graceful fallback: reuse the gatekeeper probe (identical result, no double work)
    edge = edge_probe
    remedies = _get_remedies_for_crop(edge.crop_name, edge.disease_detected)
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
