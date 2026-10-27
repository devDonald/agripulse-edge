"""AgriPulse Edge: Dial transport integration (getdial.ai).

Dial gives the agent a REAL phone number with WhatsApp + voice + SMS on the
same line — the transport your Meta WhatsApp Cloud code simulates. A farmer
sends a leaf photo, the media array lands on message.received, and an audio
reply goes out as a voice note. An offline farmer gets a plain phone call
reading the treatment aloud. No data needed on their side either way.

Docs: https://docs.getdial.ai  |  API base: https://api.getdial.ai
Env: DIAL_API_KEY (sk_live_...), DIAL_NUMBER (your Dial line),
     DIAL_WEBHOOK_SECRET (optional HMAC check on inbound events).
"""
import base64
import logging
import os
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("agripulse.dial")

DIAL_API_BASE = os.getenv("DIAL_API_BASE", "https://api.getdial.ai").rstrip("/")
DIAL_API_KEY = os.getenv("DIAL_API_KEY", "")
DIAL_NUMBER = os.getenv("DIAL_NUMBER", "")
DIAL_WEBHOOK_SECRET = os.getenv("DIAL_WEBHOOK_SECRET", "")
DIAL_TIMEOUT = float(os.getenv("DIAL_TIMEOUT", "30"))


def dial_configured() -> bool:
    return bool(DIAL_API_KEY.strip() and DIAL_NUMBER.strip())


def _headers() -> Dict[str, str]:
    return {"Authorization": f"Bearer {DIAL_API_KEY}", "Content-Type": "application/json"}


async def dial_send_text(to: str, body: str, channel: str = "whatsapp") -> Dict[str, Any]:
    """Sends a text message via Dial (WhatsApp default, falls back to SMS)."""
    if not dial_configured():
        logger.info(f"[DIAL SIMULATED text -> {to} via {channel}]:\n{body[:300]}")
        return {"simulated": True, "to": to, "channel": channel}
    payload: Dict[str, Any] = {"from": DIAL_NUMBER, "to": to, "body": body}
    if channel:
        payload["channel"] = channel
    async with httpx.AsyncClient(timeout=DIAL_TIMEOUT) as client:
        resp = await client.post(f"{DIAL_API_BASE}/api/v1/messages", headers=_headers(), json=payload)
        if resp.status_code not in (200, 201, 202):
            raise RuntimeError(f"Dial send failed {resp.status_code}: {resp.text[:300]}")
        return resp.json()


async def dial_send_audio(to: str, audio_bytes: bytes, filename: str = "advisory.mp3",
                         channel: str = "whatsapp", caption: str = "") -> Dict[str, Any]:
    """Sends an audio file as a voice note (WhatsApp) or MMS attachment."""
    if not dial_configured():
        logger.info(f"[DIAL SIMULATED voice note -> {to}]: {len(audio_bytes)} bytes")
        return {"simulated": True, "to": to, "bytes": len(audio_bytes)}
    payload: Dict[str, Any] = {
        "from": DIAL_NUMBER, "to": to, "channel": channel,
        "media": [{"filename": filename,
                   "content_base64": base64.b64encode(audio_bytes).decode(),
                   "content_type": "audio/mpeg"}],
    }
    if caption:
        payload["body"] = caption
    async with httpx.AsyncClient(timeout=DIAL_TIMEOUT) as client:
        resp = await client.post(f"{DIAL_API_BASE}/api/v1/messages", headers=_headers(), json=payload)
        if resp.status_code not in (200, 201, 202):
            raise RuntimeError(f"Dial voice-note send failed {resp.status_code}: {resp.text[:300]}")
        return resp.json()


async def dial_place_call(to: str, instruction: str,
                         voice: Optional[str] = None) -> Dict[str, Any]:
    """Rings the farmer and reads `instruction` aloud (offline-week fallback)."""
    if not dial_configured():
        logger.info(f"[DIAL SIMULATED call -> {to}]: {instruction[:200]}")
        return {"simulated": True, "to": to}
    payload: Dict[str, Any] = {"from": DIAL_NUMBER, "to": to, "instruction": instruction}
    if voice:
        payload["voice"] = voice
    async with httpx.AsyncClient(timeout=DIAL_TIMEOUT) as client:
        resp = await client.post(f"{DIAL_API_BASE}/api/v1/calls", headers=_headers(), json=payload)
        if resp.status_code not in (200, 201, 202):
            raise RuntimeError(f"Dial call failed {resp.status_code}: {resp.text[:300]}")
        return resp.json()


async def dial_fetch_media(media_url: str) -> bytes:
    """Downloads a leaf photo from a Dial message.received media array entry."""
    headers = {"Authorization": f"Bearer {DIAL_API_KEY}"} if DIAL_API_KEY else {}
    async with httpx.AsyncClient(timeout=DIAL_TIMEOUT) as client:
        resp = await client.get(media_url, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"Dial media fetch failed {resp.status_code}")

def _first(d: Dict[str, Any], *keys: str, default=None):
    for k in keys:
        if isinstance(d, dict) and d.get(k) is not None:
            return d[k]
    return default


async def process_dial_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handles a Dial webhook event. Photo -> diagnose -> voice note; text -> advisory."""
    from backend.services.crop_diagnostician import diagnose_image
    from backend.services.leaf_segmenter import segment_leaf_damage
    from backend.services.multilingual_advisor import generate_advisory, normalize_language
    from backend.services.voice_synthesizer import synthesize_spoken_audio

    try:
        msg = event.get("message", event) if isinstance(event.get("message"), dict) else event.get("data", event)
        if not isinstance(msg, dict):
            msg = event
        sender = _first(msg, "from", "sender", "fromNumber", default="unknown")
        text = _first(msg, "body", "text", "transcript", default="") or ""
        if isinstance(text, dict):
            text = text.get("body", "") or ""
        media: List[Any] = _first(msg, "media", "attachments", default=[]) or []
        language = normalize_language(
            _first(event, "language", default=_first(msg, "language", default="pidgin"))
        )

        image_bytes: Optional[bytes] = None
        for item in media:
            if isinstance(item, dict):
                if item.get("content_base64"):
                    try:
                        image_bytes = base64.b64decode(item["content_base64"])
                        break
                    except Exception:
                        continue
                url = item.get("url") or item.get("mediaUrl") or item.get("src")
                ctype = (item.get("content_type") or item.get("contentType") or "").lower()
                if url and ("image" in ctype or not ctype):
                    image_bytes = await dial_fetch_media(url)
                    break
        if image_bytes is None and isinstance(event.get("image_base64"), str):
            image_bytes = base64.b64decode(event["image_base64"])

        if image_bytes:
            diag = await diagnose_image(image_bytes, "image/jpeg")
            try:
                seg = segment_leaf_damage(image_bytes)
                damage = seg.get("damage_percentage", diag.damage_percentage)
            except Exception:
                damage = diag.damage_percentage
            ctx = {"crop_name": diag.crop_name, "disease_detected": diag.disease_detected,
                   "damage_percentage": damage, "severity": str(diag.severity)}
            query = (text.strip() or
                     f"My {diag.crop_name} leaf get problem, wetin I fit do with neem leaves?")
            advisory = await generate_advisory(query, language, ctx)
            caption = (f"AgriPulse: {diag.crop_name.title()} — {diag.disease_detected} "
                       f"({damage}% damage). Voice note get full treatment.")
            audio = synthesize_spoken_audio(advisory.spoken_reply, advisory.detected_language)
            await dial_send_audio(sender, audio, caption=caption)
            return {"status": "replied", "type": "dial_image_diagnosis",
                    "to": sender, "crop": diag.crop_name,
                    "disease": diag.disease_detected, "damage": damage,
                    "language": advisory.detected_language,
                    "voice_note_bytes": len(audio)}

        if text.strip():
            advisory = await generate_advisory(text.strip(), language, None)
            audio = synthesize_spoken_audio(advisory.spoken_reply, advisory.detected_language)
            await dial_send_audio(sender, audio, caption=f"AgriPulse: {advisory.spoken_reply[:120]}")
            return {"status": "replied", "type": "dial_text_advisory",
                    "to": sender, "language": advisory.detected_language,
                    "voice_note_bytes": len(audio)}

        return {"status": "ignored", "reason": "no image or text in event"}
    except Exception as e:
        logger.error(f"Dial event failed: {e}")
        return {"status": "error", "error": str(e)[:300]}


async def ring_farmer_with_treatment(to: str, crop: str, disease: str, damage,
                                     steps: List[str], language: str = "pidgin") -> Dict[str, Any]:
    """Outbound fallback call: reads the treatment slip aloud for an offline farmer."""
    lines = [f"Hello! This is AgriPulse farm doctor. Your {crop} get {disease}, "
             f"damage na {damage} percent. No worry. Do these steps today."]
    lines += [f"Step {i + 1}: {s}" for i, s in enumerate(steps[:4])]
    lines.append("We go check again in four days. Bye bye.")
    return await dial_place_call(to, " ".join(lines))
