"""AgriPulse Edge: canonical Meta model registry (dev.meta.ai).

Single source of truth for every Meta model the app can trigger live,
so the usage dashboard lights up with real, attributable calls.

Cloud IDs are the VERIFIED live dev.meta.ai catalog (probed 2026-10-26):
  muse-spark-1.3 / 1.2 / wonder-1.0 bill on /v1/chat/completions.
Edge IDs are local ExecuTorch bundles (never billed).
Legacy meta/llama-3.2-* aliases resolve to the live cloud flagship.
"""
from typing import Dict, List, Optional

# Live cloud models on THIS dev.meta.ai key (verified via GET /v1/models + billed pings).
CLOUD_MODEL_IDS = [
    "muse-spark-1.3",
    "muse-spark-1.2",
    "muse-wonder-1.0",
]
# On-device ExecuTorch bundles (local .pte files — zero data, never billed).
EDGE_MODEL_IDS = [
    "llama-3.2-3b-edge",
    "llama-3.2-1b-edge",
]
SEG_MODEL_ID = "sam-2-hiera-large"

META_MODEL_IDS = CLOUD_MODEL_IDS + EDGE_MODEL_IDS + [SEG_MODEL_ID]

# Back-compat: old hackathon IDs map to live equivalents.
LEGACY_ALIASES = {
    "meta/llama-3.2-90b-vision-instruct": "muse-spark-1.3",
    "meta/llama-3.2-11b-vision-instruct": "muse-spark-1.2",
    "meta/llama-3.2-3b-instruct": "llama-3.2-3b-edge",
    "meta/llama-3.2-1b-instruct": "llama-3.2-1b-edge",
    "meta/sam-2-hiera-large": "sam-2-hiera-large",
}

MODEL_CATALOG: List[Dict] = [
    {
        "id": "muse-spark-1.3",
        "label": "Muse Spark 1.3 (Cloud — Flagship Meta Muse Reasoning & Diagnosis)",
        "family": "muse-cloud",
        "tier": "cloud",
        "tokens": 1240,
        "latency": "1.4s",
        "depth": "high",
        "data_kb": "~180",
        "supports": ["diagnose", "advisory"],
    },
    {
        "id": "muse-spark-1.2",
        "label": "Muse Spark 1.2 (Cloud — Fast Vision & Multilingual Processing)",
        "family": "muse-cloud",
        "tier": "cloud",
        "tokens": 640,
        "latency": "0.7s",
        "depth": "medium",
        "data_kb": "~120",
        "supports": ["diagnose", "advisory"],
    },
    {
        "id": "muse-wonder-1.0",
        "label": "Muse Wonder 1.0 (Cloud — Meta Autonomous Agent & Advisory)",
        "family": "muse-cloud",
        "tier": "cloud",
        "tokens": 480,
        "latency": "1.2s",
        "depth": "agentic",
        "data_kb": "~120",
        "supports": ["diagnose", "advisory"],
    },
    {
        "id": "llama-3.2-3b-edge",
        "label": "Llama 3.2 3B Edge (Meta ExecuTorch On-Device INT8)",
        "family": "edge",
        "tier": "edge",
        "tokens": 180,
        "latency": "38ms",
        "depth": "field",
        "data_kb": "0",
        "supports": ["diagnose", "advisory"],
    },
    {
        "id": "llama-3.2-1b-edge",
        "label": "Llama 3.2 1B Edge (Meta ExecuTorch On-Device INT4)",
        "family": "edge",
        "tier": "edge",
        "tokens": 120,
        "latency": "61ms",
        "depth": "field",
        "data_kb": "0",
        "supports": ["diagnose", "advisory"],
    },
    {
        "id": "sam-2-hiera-large",
        "label": "SAM 2 Hiera Large (Meta Segment Anything 2 Lesion Masking)",
        "family": "segment",
        "tier": "cloud",
        "tokens": 0,
        "latency": "45ms",
        "depth": "mask",
        "data_kb": "~90",
        "supports": ["segment"],
    },
]

BY_ID: Dict[str, Dict] = {m["id"]: m for m in MODEL_CATALOG}
DEFAULT_MODEL_ID = "muse-spark-1.3"
EDGE_MODEL_ID = "llama-3.2-3b-edge"
SAM_MODEL_ID = "sam-2-hiera-large"

VISION_MODEL_IDS = tuple(CLOUD_MODEL_IDS)


def resolve_model(model_id: Optional[str], offline: bool = False) -> Dict:
    """Resolve a requested model_id to a catalog entry, with safe fallbacks."""
    if offline:
        return BY_ID[EDGE_MODEL_ID]
    if model_id in LEGACY_ALIASES:
        model_id = LEGACY_ALIASES[model_id]
    if model_id in BY_ID:
        return BY_ID[model_id]
    return BY_ID[DEFAULT_MODEL_ID]


def is_cloud_vision(model_id: str) -> bool:
    mid = LEGACY_ALIASES.get(model_id, model_id)
    return mid in VISION_MODEL_IDS


def is_edge(model_id: str) -> bool:
    mid = LEGACY_ALIASES.get(model_id, model_id)
    return mid in EDGE_MODEL_IDS
