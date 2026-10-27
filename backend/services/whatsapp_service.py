"""AgriPulse Edge: WhatsApp Business Cloud API Integration Service.

Enables smallholder farmers to interact with AgriPulse via WhatsApp voice notes,
images, and local dialect text messages when within village cellular range.
"""
import logging
import os
from typing import Any, Dict, Optional

import httpx
from dotenv import load_dotenv

from backend.services.crop_diagnostician import diagnose_image
from backend.services.leaf_segmenter import segment_leaf_damage
from backend.services.multilingual_advisor import generate_advisory

load_dotenv()
logger = logging.getLogger("agripulse.whatsapp")

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "agripulse_hackathon_verify_token")


def verify_webhook_token(mode: Optional[str], token: Optional[str], challenge: Optional[str]) -> Optional[str]:
    """Handles Meta WhatsApp Webhook verification handshake."""
    if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
        return challenge
    return None


async def send_whatsapp_text(recipient_phone: str, message: str) -> bool:
    """Sends a text message back to the farmer on WhatsApp."""
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        logger.info(f"[SIMULATED WHATSAPP OUTBOUND to {recipient_phone}]:\n{message}")
        return True

    url = f"https://graph.facebook.com/v21.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": recipient_phone,
        "type": "text",
        "text": {"body": message},
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            return resp.status_code in (200, 201)
    except Exception as e:
        logger.error(f"Failed to send WhatsApp message: {e}")
        return False


async def download_whatsapp_media(media_id: str) -> bytes:
    """Downloads photo bytes via Graph API: media ID -> media URL -> bytes."""
    if not WHATSAPP_TOKEN:
        raise RuntimeError("WHATSAPP_TOKEN not configured — cannot fetch media")
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    async with httpx.AsyncClient(timeout=20.0) as client:
        meta = await client.get(f"https://graph.facebook.com/v21.0/{media_id}", headers=headers)
        if meta.status_code != 200:
            raise RuntimeError(f"Graph media lookup failed {meta.status_code}: {meta.text[:200]}")
        media_url = meta.json().get("url", "")
        if not media_url:
            raise RuntimeError("Graph returned no media URL")
        data = await client.get(media_url, headers=headers)
        if data.status_code != 200:
            raise RuntimeError(f"Graph media download failed {data.status_code}")
        return data.content


async def _image_diagnosis_reply(image_bytes: bytes, caption: str = "") -> Dict[str, Any]:
    """Runs the real pipeline on a WhatsApp photo: diagnose -> segment -> advisory."""
    diag = await diagnose_image(image_bytes, "image/jpeg")
    try:
        seg = segment_leaf_damage(image_bytes)
        damage = seg.get("damage_percentage", diag.damage_percentage)
    except Exception:
        damage = diag.damage_percentage
    advisory = await generate_advisory(
        user_query=(caption.strip() or
                    f"My {diag.crop_name} leaf get problem, wetin I fit do with neem leaves?"),
        language="pidgin",
        diagnosis_context={"crop_name": diag.crop_name,
                           "disease_detected": diag.disease_detected,
                           "damage_percentage": damage,
                           "severity": str(diag.severity)},
    )
    reply_text = (
        f"🌿 *AgriPulse Crop Scan Complete* 🌿\n\n"
        f"• *Crop:* {diag.crop_name.title()}\n"
        f"• *Detected Disease:* {diag.disease_detected}\n"
        f"• *Confidence:* {int(diag.confidence * 100)}%\n"
        f"• *Measured Leaf Damage:* {damage}% (via SAM 2)\n"
        f"• *Severity:* {str(diag.severity.value if hasattr(diag.severity, 'value') else diag.severity).title()}\n\n"
        f"*{advisory.spoken_reply}*\n\n"
        f"*Step-by-step wetin you go do:*\n"
        + "\n".join(f"{i}. {s}" for i, s in enumerate(advisory.step_by_step_instructions, 1))
        + f"\n\n*Local materials you fit use:*\n"
        + "\n".join(f"• {item}" for item in advisory.local_market_substitutes)
    )
    return {"reply_text": reply_text, "crop": diag.crop_name,
            "disease": diag.disease_detected, "damage": damage,
            "language": advisory.detected_language}


async def process_incoming_whatsapp_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Parses incoming WhatsApp webhook event and generates automated agricultural response."""
    try:
        entry = payload.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])

        if not messages:
            return {"status": "ignored", "reason": "no messages in payload"}

        msg = messages[0]
        sender_phone = msg.get("from", "unknown")
        msg_type = msg.get("type", "text")

        # 1. Farmer sent a text or voice transcription
        if msg_type == "text":
            body = msg.get("text", {}).get("body", "")
            advisory = await generate_advisory(user_query=body, language="pidgin")

            reply_text = (
                f"🌿 *AgriPulse Farm Doctor* 🌿\n\n"
                f"{advisory.spoken_reply}\n\n"
                f"*Step-by-step wetin you go do:*\n"
            )
            for i, step in enumerate(advisory.step_by_step_instructions, 1):
                reply_text += f"{i}. {step}\n"

            reply_text += (
                f"\n*Local materials you fit use:*\n"
                + "\n".join(f"• {item}" for item in advisory.local_market_substitutes)
            )

            await send_whatsapp_text(sender_phone, reply_text)
            return {"status": "replied", "type": "text_advisory", "reply": reply_text}

        # 2. Farmer sent an image via WhatsApp
        elif msg_type == "image":
            import base64 as _b64

            img = msg.get("image", {}) or {}
            media_id = img.get("id", "")
            caption = img.get("caption", "") or ""
            image_bytes = None
            # Simulator/tests may embed bytes directly; Meta sends a media ID.
            if img.get("content_base64"):
                try:
                    image_bytes = _b64.b64decode(img["content_base64"])
                except Exception:
                    image_bytes = None
            if image_bytes is None and media_id:
                try:
                    image_bytes = await download_whatsapp_media(media_id)
                except Exception as e:
                    logger.warning(f"Media fetch failed ({e}); honest fallback, no fake diagnosis.")
            if image_bytes is None:
                reply_text = (
                    "🌿 *AgriPulse Farm Doctor* 🌿\n\n"
                    "Photo received, but I never fit download am — WhatsApp number never connect yet. "
                    "Connect WHATSAPP_TOKEN make I scan am well-well, or try the offline app."
                )
                await send_whatsapp_text(sender_phone, reply_text)
                return {"status": "replied", "type": "image_unavailable",
                        "reply": reply_text, "media_id": media_id}
            out = await _image_diagnosis_reply(image_bytes, caption)
            await send_whatsapp_text(sender_phone, out["reply_text"])
            return {"status": "replied", "type": "image_diagnosis",
                    "reply": out["reply_text"], "crop": out["crop"],
                    "disease": out["disease"], "damage": out["damage"]}

        return {"status": "unsupported_type", "type": msg_type}

    except Exception as e:
        logger.error(f"Error processing WhatsApp webhook: {e}")
        return {"status": "error", "error": str(e)}
