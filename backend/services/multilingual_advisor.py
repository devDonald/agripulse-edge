"""Multilingual Voice & Advisory Copilot (Nigerian Pidgin, Hausa, Yoruba, English)."""
import asyncio
import json
import logging
import os
import re
from typing import List, Literal, Optional

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from backend.services.meta_models import is_edge as _is_edge_model, resolve_model as _resolve_model

load_dotenv()
logger = logging.getLogger("agripulse.advisor")

META_API_URL = os.getenv(
    "META_API_URL", "https://api.meta.ai/v1/chat/completions"
)
META_API_KEY = os.getenv("META_API_KEY") or os.getenv("MODEL_API_KEY", "")
META_MODEL = os.getenv("META_MODEL", "muse-spark-1.3")
META_TIMEOUT = float(os.getenv("META_TIMEOUT", "60"))
MOCK_MODE = os.getenv("MOCK_MODE", "false").lower() in ("1", "true", "yes")

Lang = Literal["pidgin", "hausa", "yoruba", "english"]


class AdvisoryResponse(BaseModel):
    detected_language: Lang
    spoken_reply: str = Field(..., min_length=10)
    step_by_step_instructions: List[str] = Field(..., min_length=3)
    preventative_cultural_practices: List[str] = Field(..., min_length=1)
    local_market_substitutes: List[str] = Field(..., min_length=1)
    audio_base64: Optional[str] = Field(
        default=None, description="Simulated audio speech waveform in base64"
    )


def normalize_language(raw: str) -> Lang:
    s = (raw or "pidgin").strip().lower()
    if s in ("pcm", "naija", "nigerian pidgin", "pidgin", "pidgin english", "broken"):
        return "pidgin"
    if s in ("ha", "hausa", "hausawa"):
        return "hausa"
    if s in ("yo", "yoruba", "yorùbá"):
        return "yoruba"
    return "english"


ADVISOR_SYSTEM = (
    "You are the AgriPulse Edge Voice Copilot, a warm, culturally empathetic agricultural extension officer "
    "working directly with smallholder farmers in West Africa (Nigeria, Ghana, Cameroon).\n\n"
    "COMMUNICATION RULES:\n"
    "1. Respond directly in the requested language/dialect:\n"
    "   - 'pidgin': Authentic Nigerian Pidgin (e.g., 'How body my friend! No let this cassava leaf worry your mind...').\n"
    "   - 'hausa': Natural northern Nigerian Hausa for farming communities.\n"
    "   - 'yoruba': Respectful southwestern Nigerian Yoruba.\n"
    "   - 'english': Simple, warm plain English without academic jargon.\n"
    "2. spoken_reply: 2-4 sentences. Warm greeting, validate the farmer's concern, name the crop and issue, "
    "and give one reassuring action they can execute today before dark.\n"
    "3. step_by_step_instructions: 3-5 numbered, concrete steps using local units (handfuls, 5-litre paint bucket, "
    "borehole water, local black soap as a sticker, sunset spraying).\n"
    "4. preventative_cultural_practices: 3-4 proactive habits (crop roguing, ash water tool cleaning, spacing).\n"
    "5. local_market_substitutes: 3-4 accessible substitutes (wood ash, chili-garlic, pawpaw leaf ferment).\n\n"
    "Return STRICT JSON ONLY, no markdown. Schema: { 'detected_language': 'pidgin'|'hausa'|'yoruba'|'english', "
    "'spoken_reply': string, 'step_by_step_instructions': [string], "
    "'preventative_cultural_practices': [string], 'local_market_substitutes': [string] }"
)


def _mock_advisory(query: str, lang: Lang, ctx: Optional[dict]) -> AdvisoryResponse:
    crop = (ctx or {}).get("crop_name", "cassava").capitalize()
    disease = (ctx or {}).get("disease_detected", "Cassava Mosaic Disease")

    spoken_replies = {
        "pidgin": (
            f"How body my friend! For this your {crop} wey {disease} dey disturb, "
            f"no shake at all. You fit prepare sweet neem leaf medicine this evening, "
            f"and your farm go bounce back strong!"
        ),
        "hausa": (
            f"Sannu abokina manomi! Wannan cutar {crop} wato {disease}, "
            f"ana iya magance ta da ruwan ganyen neem a yau. "
            f"Kada ka damu ko kadan, amfanin gonarka zai dawo da karfi."
        ),
        "yoruba": (
            f"Ẹ ku ojumo ore mi agbẹ! Fun arun {crop} yi ({disease}), "
            f"e ma se aibalẹ rara. Ẹ le se omi ewe neem ni irole oni, "
            f"oko yin yio si tun gberu si."
        ),
        "english": (
            f"Good day my friend! Regarding this {crop} affected by {disease}, "
            f"do not lose hope. You can prepare an organic neem spray today "
            f"to protect your harvest and clear the infestation."
        ),
    }

    instructions = {
        "pidgin": [
            "Pluck 2 full handfuls of fresh green neem leaves (dogonyaro) from tree.",
            "Pound am well inside mortar, then soak am inside 5-litre paint rubber of clean water overnight.",
            "Sieve the green water tomorrow morning, then add half teaspoon of local black soap (ose dudu) make e hold leaf body.",
            "Take hand sprayer spray both top and under the leaves once every 4 days when sun don go down.",
        ],
        "hausa": [
            "Tattara ganyen dogonyaro guda biyu masu kyau daga bishiya.",
            "Daka su a turmi, sannan a jika a cikin bokitin lita 5 na ruwa mai tsafta dare daya.",
            "Tace ruwan da safe, sannan a zuba sabulun salo kadan don ya kama jikin ganye.",
            "Fesa a karkashin ganyayyaki sau daya a kowane kwana hudu da yamma bayan rana ta fadi.",
        ],
        "yoruba": [
            "Kojo ewe dogonyaro (neem) meji ti o tutu daradara.",
            "Gun un ninu odo, ki o si re sinu garawa omi lita marun fun odidi ojo kan.",
            "Se omi naa, fi ose dudu die si ki o le ba rọ mọ ara ewe.",
            "Fun sokiri si abe ati oke awon ewe ni irole nigbati oorun ba ti wọ.",
        ],
        "english": [
            "Gather 2 large handfuls of fresh green neem leaves (Azadirachta indica).",
            "Crush thoroughly in a mortar and steep in a 5-litre bucket of clean borehole water for 12 hours.",
            "Strain the liquid through a fine cloth, then dissolve half a teaspoon of local black soap as a natural wetting agent.",
            "Spray thoroughly on the undersides of leaves every 4 days during late afternoon to prevent evaporation.",
        ],
    }

    preventative = [
        "Rotate this farm plot with maize, cowpea, or groundnut next planting season.",
        "Rogue (uproot) severely stunted infected plants and burn or bury far away from field.",
        "Space plant cuttings at least 1m x 1m apart to improve ventilation and reduce pest humidity.",
        "Clean all cutlasses and hoes in ash water before moving to an uninfected farm section.",
    ]

    substitutes = [
        "Sieved dry wood ash dusting at early dawn while leaves have dew.",
        "Hot chili pepper and crushed garlic emulsion as insect deterrent.",
        "Fermented mature pawpaw (papaya) leaf extract as natural bio-fungicide.",
    ]

    return AdvisoryResponse(
        detected_language=lang,
        spoken_reply=spoken_replies[lang],
        step_by_step_instructions=instructions.get(lang, instructions["english"]),
        preventative_cultural_practices=preventative,
        local_market_substitutes=substitutes,
    )


def _extract_json(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not m:
        raise ValueError(f"Model did not return JSON: {text[:500]}")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        fixed = re.sub(r",\s*([\]}])", r"\1", m.group(0))
        return json.loads(fixed)


async def generate_advisory(
    user_query: str,
    language: str = "pidgin",
    diagnosis_context: Optional[dict] = None,
    model_id: Optional[str] = None,
    use_live: bool = False,
) -> AdvisoryResponse:
    if not user_query or not user_query.strip():
        raise ValueError("User query cannot be empty")

    lang = normalize_language(language)
    spec = _resolve_model(model_id)
    active_model = spec["id"]

    if _is_edge_model(active_model) or ((MOCK_MODE and not use_live) or not META_API_KEY):
        out = _mock_advisory(user_query, lang, diagnosis_context)
        if _is_edge_model(active_model):
            out.audio_base64 = None
        return out

    ctx_str = json.dumps(diagnosis_context or {}, ensure_ascii=False)[:2000]
    user_msg = (
        f"Language: {lang}\n"
        f"Farmer spoken inquiry: {user_query}\n"
        f"Diagnostic context from field scan: {ctx_str}\n\n"
        f"Generate empathetic extension guidance strictly in {lang}."
    )

    payload = {
        "model": active_model,
        "messages": [
            {"role": "system", "content": ADVISOR_SYSTEM},
            {"role": "user", "content": user_msg},
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
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=META_TIMEOUT) as client:
                resp = await client.post(META_API_URL, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    parsed = _extract_json(content)
                    parsed.setdefault("detected_language", lang)
                    return AdvisoryResponse(**parsed)
                last_error = f"Meta API {resp.status_code}: {resp.text[:500]}"
        except Exception as e:
            last_error = str(e)
            await asyncio.sleep(0.5)

    logger.warning(f"Meta API advisory failed ({last_error}), falling back to dialect template.")
    return _mock_advisory(user_query, lang, diagnosis_context)
