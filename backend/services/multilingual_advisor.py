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

Lang = Literal["english", "pidgin", "hausa", "yoruba", "igbo"]


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
    s = (raw or "english").strip().lower()
    if s in ("pcm", "naija", "nigerian pidgin", "pidgin", "pidgin english", "broken"):
        return "pidgin"
    if s in ("ha", "hausa", "hausawa"):
        return "hausa"
    if s in ("yo", "yoruba", "yorùbá"):
        return "yoruba"
    if s in ("ig", "igbo", "ibo", "ndi igbo", "asusu igbo"):
        return "igbo"
    return "english"


ADVISOR_SYSTEM = (
    "You are the AgriPulse Edge Voice Copilot, a warm, culturally empathetic agricultural extension officer "
    "speaking directly with smallholder farmers in Nigeria.\n\n"
    "COMMUNICATION RULES:\n"
    "1. Respond directly in the requested language/dialect with authentic Nigerian flavor, rhythm, and local expressions:\n"
    "   - 'english': Warm Nigerian / West African English with clear, respectful cadence and local farming terminology.\n"
    "   - 'pidgin': Vibrant, natural Nigerian Pidgin with authentic cadence and reassuring phrasing "
    "(e.g., 'How body, my person! No let this sickness shake your heart at all-o. Make you listen well-well: "
    "this evening before sunset, take fresh neem water spray both top and under the leaf. Your farm go dey alright!').\n"
    "   - 'hausa': Respectful, natural northern Nigerian Hausa for farming communities (e.g. 'Sannu abokina manomi! Kada ka damu...').\n"
    "   - 'yoruba': Warm, respectful southwestern Nigerian Yoruba (e.g. 'Ẹ ku ojumo ore mi agbẹ! Ẹ ma se aibalẹ rara...').\n"
    "   - 'igbo': Respectful, warm southeastern Nigerian Igbo for farming communities (e.g. 'Nnọọ nwanne m onye ọrụ ugbo! Atụla egwu ma ọlị...').\n"
    "2. spoken_reply: 2-3 short, rhythmic sentences meant to be SPOKEN aloud as a voice note. "
    "Do NOT include Latin botanical names, parentheses, or complex acronyms in spoken_reply. "
    "Give a warm greeting, validate the farmer, name the issue simply, and give one concrete action they can take today.\n"
    "3. step_by_step_instructions: 3-5 numbered, concrete steps using local units (handfuls, 5-litre paint bucket, "
    "borehole water, local black soap as a sticker, sunset spraying).\n"
    "4. preventative_cultural_practices: 3-4 proactive habits (crop roguing, ash water tool cleaning, spacing).\n"
    "5. local_market_substitutes: 3-4 accessible substitutes (wood ash, chili-garlic, pawpaw leaf ferment).\n"
    "6. NON-LEAF / RETAKE CASES: If crop_name is 'unknown' or disease_detected indicates 'No crop leaf detected' "
    "(or if the photo is of a non-crop object like a book, tool, wall, or person), DO NOT prescribe agricultural sprays, "
    "neem, wood ash, or roguing. Instead, kindly and warmly inform the farmer in their language that the picture does not "
    "show a crop leaf, and provide clear step-by-step guidance on how to take a clear, well-lit photo of an actual crop leaf in the field.\n\n"
    "Return STRICT JSON ONLY, no markdown. Schema: { 'detected_language': 'english'|'pidgin'|'hausa'|'yoruba'|'igbo', "
    "'spoken_reply': string, 'step_by_step_instructions': [string], "
    "'preventative_cultural_practices': [string], 'local_market_substitutes': [string] }"
)


def _mock_advisory(query: str, lang: Lang, ctx: Optional[dict]) -> AdvisoryResponse:
    crop_raw = str((ctx or {}).get("crop_name", "cassava")).strip().lower()
    raw_disease = str((ctx or {}).get("disease_detected", "Cassava Mosaic Disease")).strip()
    is_non_leaf = (
        crop_raw in ("unknown", "other", "none", "not_a_leaf", "non_leaf")
        or "no crop leaf" in raw_disease.lower()
        or "no leaf" in raw_disease.lower()
        or "not a leaf" in raw_disease.lower()
        or "not a crop" in raw_disease.lower()
    )

    if is_non_leaf:
        spoken_replies_non_leaf = {
            "pidgin": (
                "How body my person! I no see any crop leaf for this photo wey you snap. "
                "Abeg snap clear photo of your farm crop leaf make I fit check the sickness for you."
            ),
            "hausa": (
                "Sannu abokina manomi! Ban ga ganyen amfanin gona a wannan hoton ba. "
                "Da fatan za a dauki hoton ganye mai kyau don samun magani da shawarwari."
            ),
            "yoruba": (
                "Ẹ ku ojumo ore mi agbẹ! Mi o ri ewe kankan ninu aworan yi. "
                "Ẹ jọwọ ya aworan ewe oko yin daadaa ki n le ran yin lọwọ pelu ogun to peye."
            ),
            "igbo": (
                "Nnọọ nwanne m onye ọrụ ugbo! Ahụghị m akwụkwọ ihe ubi ọ bụla na foto a. "
                "Biko sere foto doro anya nke akwụkwọ ugbo gị ka m nwee ike inyere gị aka."
            ),
            "english": (
                "Hello my friend! No crop leaf was detected in this photo. "
                "Please take a clear, well-lit photo of an actual crop leaf so I can identify the disease and guide you."
            ),
        }
        instructions_non_leaf = {
            "pidgin": [
                "Go your farm go look the exact crop plant (Cassava, Maize, Yam, Tomato) wey get problem.",
                "Hold your phone camera close to the leaf blade (about 20 to 30 cm) under normal daylight.",
                "Make sure na the leaf dey show well-well, no let book, wall, or dark shadow cover am.",
            ],
            "hausa": [
                "Je gonarka ka nemi ainihin ganyen da ke da matsala (Rogo, Masara, Doya, Tumatir).",
                "Kusantar da wayarka kusa da ganyen a cikin hasken rana na halitta.",
                "Tabbatar ganyen yana bayyana sarai ba tare da wani abu daban ya rufe shi ba.",
            ],
            "yoruba": [
                "Ẹ lọ sinu oko yin ki ẹ wa ewe to n ṣaisan gangan (Gbaguda, Agbado, Isu, Tomato).",
                "Ẹ mu foonu yin sunmọ ewe naa daadaa labẹ imọlẹ ọjọ to mọ tọrọ.",
                "Ẹ rii daju pe ewe naa han kedere lai si nkan miran to bo o tabi iboji to le.",
            ],
            "igbo": [
                "Gaa n'ugbo gị wee chọta ezigbo akwụkwọ osisi na-arịa ọrịa (Akpụ, Ọka, Ji, Tọmatọ).",
                "Jide igwefoto ekwentị gị nso n'akwụkwọ ahụ n'okpuru ìhè anyanwụ doro anya.",
                "Hụ na akwụkwọ ahụ pụtara nke ọma na-enweghị ndo gbara ọchịchịrị ma ọ bụ ihe ọzọ na-ekpuchi ya.",
            ],
            "english": [
                "Locate the affected crop plant in your field (Cassava, Maize, Yam, Tomato, etc.).",
                "Hold your phone camera 20 to 30 cm away from a single affected leaf under natural daylight.",
                "Ensure the leaf blade fills the frame in sharp focus without heavy shadows or non-plant objects.",
            ],
        }
        preventative_non_leaf = [
            "Wipe camera lens clean to remove dust before taking crop photos.",
            "Photograph leaves during morning or late afternoon for even natural light.",
            "Inspect both the top and underside of the leaf for early disease spots.",
        ]
        substitutes_non_leaf = [
            "Natural daylight (avoid strong camera flash).",
            "Clean camera lens.",
            "Plain backing (e.g. piece of cardboard or clean hand) to help phone focus on the leaf.",
        ]
        return AdvisoryResponse(
            detected_language=lang,
            spoken_reply=spoken_replies_non_leaf[lang],
            step_by_step_instructions=instructions_non_leaf.get(lang, instructions_non_leaf["english"]),
            preventative_cultural_practices=preventative_non_leaf,
            local_market_substitutes=substitutes_non_leaf,
        )

    crop = crop_raw.capitalize()
    # Clean Latin names/parentheses for spoken naturalness
    clean_disease = re.sub(r"\([^)]*\)", "", raw_disease).strip()

    spoken_replies = {
        "pidgin": (
            f"How body, my person! For this your {crop}, wey {clean_disease} dey disturb am, "
            f"no shake at all-o! Make you listen well-well: you fit prepare sweet neem leaf medicine this evening, "
            f"and your farm go bounce back strong!"
        ),
        "hausa": (
            f"Sannu abokina manomi! Wannan cutar {crop} wato {clean_disease}, "
            f"ana iya magance ta da ruwan ganyen neem a yau. "
            f"Kada ka damu ko kadan, amfanin gonarka zai dawo da karfi."
        ),
        "yoruba": (
            f"Ẹ ku ojumo ore mi agbẹ! Fun arun {crop} yi ({clean_disease}), "
            f"e ma se aibalẹ rara. Ẹ le se omi ewe neem ni irole oni, "
            f"oko yin yio si tun gberu si."
        ),
        "igbo": (
            f"Nnọọ, nwanne m onye ọrụ ugbo! Maka ọrịa {crop} a ({clean_disease}), "
            f"atụla egwu ma ọlị. Ị nwere ike ịkwadebe ọgwụ mmiri akwụkwọ neem n'anyasị taa, "
            f"ugbo gị ga-adịkwa mma ọzọ!"
        ),
        "english": (
            f"Good day, my friend! Regarding your {crop} affected by {clean_disease}, "
            f"do not lose hope. You can prepare an organic neem spray today "
            f"to protect your harvest and clear the infection."
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
        "igbo": [
            "Gbutu akwụkwọ neem (dogonyaro) abụọ jupụtara n'aka nke dị ọhụrụ.",
            "Kpụọ ya nke ọma n'ime odu, wee tinye ya n'ime lita mmiri ise nke dị ọcha maka abalị dum.",
            "Zacha mmiri ahụ n'ụtụtụ echi, tinye obere ncha ojii ka ọ nwee ike ịrapagide n'akwụkwọ.",
            "Fesa ya n'okpuru na n'elu akwụkwọ niile n'anyasị mgbe anyanwụ dachara kwa ụbọchị anọ ọ bụla.",
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
        "max_tokens": 2500,
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
                    choice = data["choices"][0]
                    content = choice.get("message", {}).get("content") or ""
                    if not content.strip():
                        raise ValueError("Model returned empty content")
                    parsed = _extract_json(content)
                    parsed.setdefault("detected_language", lang)
                    return AdvisoryResponse(**parsed)
                last_error = f"Meta API {resp.status_code}: {resp.text[:500]}"
        except Exception as e:
            last_error = str(e)
            await asyncio.sleep(0.5)

    logger.warning(f"Meta API advisory failed ({last_error}), falling back to dialect template.")
    return _mock_advisory(user_query, lang, diagnosis_context)
