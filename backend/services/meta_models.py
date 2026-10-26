"""AgriPulse Edge: canonical Meta model registry (dev.meta.ai).

Single source of truth for every Meta model the app can trigger live,
so the usage dashboard lights up with real, attributable calls.
"""
from typing import Dict, List, Optional

# dev.meta.ai model IDs — these exact strings are sent as `model` so usage is metered.
META_MODEL_IDS = [
    "meta/llama-3.2-90b-vision-instruct",
    "meta/llama-3.2-11b-vision-instruct",
    "meta/llama-3.2-3b-instruct",
    "meta/llama-3.2-1b-instruct",
    "meta/sam-2-hiera-large",
]

MODEL_CATALOG: List[Dict] = [
    {
        "id": "meta/llama-3.2-90b-vision-instruct",
        "label": "Llama 3.2 90B Vision (Cloud — Deep Pathology Reasoning)",
        "family": "vision-cloud",
        "tier": "cloud",
        "tokens": 1240,
        "latency": "1.4s",
        "depth": "high",
        "data_kb": "~180",
        "supports": ["diagnose", "advisory"],
    },
    {
        "id": "meta/llama-3.2-11b-vision-instruct",
        "label": "Llama 3.2 11B Vision (Cloud — Fast Vision)",
        "family": "vision-cloud",
        "tier": "cloud",
        "tokens": 640,
        "latency": "0.7s",
        "depth": "medium",
        "data_kb": "~120",
        "supports": ["diagnose", "advisory"],
    },
    {
        "id": "meta/llama-3.2-3b-instruct",
        "label": "Llama 3.2 3B (ExecuTorch On-Device INT8)",
        "family": "edge",
        "tier": "edge",
        "tokens": 180,
        "latency": "38ms",
        "depth": "field",
        "data_kb": "0",
        "supports": ["diagnose", "advisory"],
    },
    {
        "id": "meta/llama-3.2-1b-instruct",
        "label": "Llama 3.2 1B (ExecuTorch On-Device INT4)",
        "family": "edge",
        "tier": "edge",
        "tokens": 120,
        "latency": "61ms",
        "depth": "field",
        "data_kb": "0",
        "supports": ["diagnose", "advisory"],
    },
    {
        "id": "meta/sam-2-hiera-large",
        "label": "SAM 2 Hiera Large (Cloud Lesion Segmentation)",
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
DEFAULT_MODEL_ID = "meta/llama-3.2-90b-vision-instruct"
EDGE_MODEL_ID = "meta/llama-3.2-3b-instruct"
SAM_MODEL_ID = "meta/sam-2-hiera-large"

VISION_MODEL_IDS = ("meta/llama-3.2-90b-vision-instruct", "meta/llama-3.2-11b-vision-instruct")
EDGE_MODEL_IDS = ("meta/llama-3.2-3b-instruct", "meta/llama-3.2-1b-instruct")


def resolve_model(model_id: Optional[str], offline: bool = False) -> Dict:
    """Resolve a requested model_id to a catalog entry, with safe fallbacks."""
    if offline:
        return BY_ID[EDGE_MODEL_ID]
    if model_id in BY_ID:
        return BY_ID[model_id]
    return BY_ID[DEFAULT_MODEL_ID]


def is_cloud_vision(model_id: str) -> bool:
    return model_id in VISION_MODEL_IDS


def is_edge(model_id: str) -> bool:
    return model_id in EDGE_MODEL_IDS
