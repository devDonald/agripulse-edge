"""AgriPulse Edge: WhatsApp Business Cloud API Integration Service.

Enables smallholder farmers to interact with AgriPulse via WhatsApp voice notes,
images, and local dialect text messages when within village cellular range.
"""
import logging
import os
import re
import time
from typing import Any, Dict, Optional

import httpx
from dotenv import load_dotenv

from backend.services.crop_diagnostician import diagnose_image, severity_for_damage
from backend.services.leaf_segmenter import segment_leaf_damage
from backend.services.multilingual_advisor import generate_advisory
from backend.services.mobile_sync import save_scan
from backend.services.voice_synthesizer import synthesize_spoken_audio

load_dotenv()
logger = logging.getLogger("agripulse.whatsapp")

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "agripulse_hackathon_verify_token")
_processed_messages: Dict[str, float] = {}


def _message_language(text: str) -> str:
    low = (text or "").lower()
    if re.search(r"\b(igbo|ibo|nnọọ|nnoo|kedu|ugbo|akwukwo|akwụkwọ|ọrịa|oria|ogwu|ọgwụ|daalu)\b", low):
        return "igbo"
    if re.search(r"\b(hausa|sannu|yaya|ganye|magani)\b", low):
        return "hausa"
    if re.search(r"\b(yoruba|bawo|ewe|ọ|ẹ|à|ṣ)\b", low):
        return "yoruba"
    if re.search(r"\b(english|please|what|how)\b", low):
        return "english"
    return "pidgin"


def _claim_message(message_id: str) -> bool:
    """Ignore webhook retries while keeping the process-local cache bounded."""
    now = time.time()
    for key, seen in list(_processed_messages.items()):
        if now - seen > 86400:
            _processed_messages.pop(key, None)
    if message_id and message_id in _processed_messages:
        return False
    if message_id:
        _processed_messages[message_id] = now
    return True


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


async def send_whatsapp_voice(recipient_phone: str, audio_bytes: bytes) -> bool:
    """Uploads an MP3 and sends it as a WhatsApp audio response."""
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        logger.info("[SIMULATED WHATSAPP VOICE to %s]: %d bytes", recipient_phone, len(audio_bytes))
        return True
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    base = f"https://graph.facebook.com/v21.0/{WHATSAPP_PHONE_NUMBER_ID}"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            upload = await client.post(
                f"{base}/media", headers=headers,
                data={"messaging_product": "whatsapp", "type": "audio/mpeg"},
                files={"file": ("agripulse-advice.mp3", audio_bytes, "audio/mpeg")},
            )
            if upload.status_code not in (200, 201):
                logger.error("WhatsApp media upload failed: %s", upload.text[:300])
                return False
            sent = await client.post(
                f"{base}/messages",
                headers={**headers, "Content-Type": "application/json"},
                json={"messaging_product": "whatsapp", "to": recipient_phone, "type": "audio",
                      "audio": {"id": upload.json().get("id")}},
            )
            return sent.status_code in (200, 201)
    except Exception as exc:
        logger.error("Failed to send WhatsApp voice response: %s", exc)
        return False


WHATSAPP_MEDIA_HOSTS = ("lookaside.fbsbx.com", "scontent.xx.fbcdn.net", ".fbcdn.net", "fbcdn.net")


async def download_whatsapp_media(media_id: str) -> bytes:
    """Downloads photo bytes via Graph API: media ID -> media URL -> bytes.

    The returned media URL must land on Meta CDN hosts (SSRF guard), and the
    download is streamed with a 10MB cap plus image validation — a forged
    webhook must not turn this server into a proxy or memory bomb.
    """
    import io as _io

    from PIL import Image as _Image

    if not WHATSAPP_TOKEN:
        raise RuntimeError("WHATSAPP_TOKEN not configured — cannot fetch media")
    if not media_id or not media_id.replace("-", "").replace("_", "").isalnum():
        raise RuntimeError("Invalid WhatsApp media ID")
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    async with httpx.AsyncClient(timeout=20.0) as client:
        meta = await client.get(f"https://graph.facebook.com/v21.0/{media_id}", headers=headers)
        if meta.status_code != 200:
            raise RuntimeError(f"Graph media lookup failed {meta.status_code}: {meta.text[:200]}")
        media_url = meta.json().get("url", "") or ""
        from urllib.parse import urlparse as _urlparse

        host = (_urlparse(media_url).netloc or "").lower()
        if _urlparse(media_url).scheme != "https" or not any(
            host == h or host.endswith(h) for h in WHATSAPP_MEDIA_HOSTS
        ):
            raise RuntimeError("WhatsApp media host not allowlisted")
        total = 0
        chunks = []
        async with client.stream("GET", media_url, headers=headers) as data:
            if data.status_code != 200:
                raise RuntimeError(f"Graph media download failed {data.status_code}")
            async for chunk in data.aiter_bytes(65536):
                total += len(chunk)
                if total > 10 * 1024 * 1024:
                    raise RuntimeError("WhatsApp media exceeds size cap")
                chunks.append(chunk)
        raw = b"".join(chunks)
    try:
        with _Image.open(_io.BytesIO(raw)) as probe:
            probe.verify()
    except Exception:
        raise RuntimeError("WhatsApp media is not a decodable image")
    return raw


async def _image_diagnosis_reply(image_bytes: bytes, caption: str = "") -> Dict[str, Any]:
    """Runs the real pipeline on a WhatsApp photo: diagnose -> segment -> advisory."""
    diag = await diagnose_image(image_bytes, "image/jpeg")
    try:
        seg = segment_leaf_damage(image_bytes)
        damage = int(round(float(seg.get("damage_percentage", diag.damage_percentage))))
    except Exception:
        damage = int(round(float(diag.damage_percentage)))
    severity = severity_for_damage(float(damage)).value
    language = _message_language(caption)
    advisory = await generate_advisory(
        user_query=(caption.strip() or
                    f"My {diag.crop_name} leaf get problem, wetin I fit do with neem leaves?"),
        language=language,
        diagnosis_context={"crop_name": diag.crop_name,
                           "disease_detected": diag.disease_detected,
                           "damage_percentage": damage,
                           "severity": severity},
    )
    clean_disease = re.sub(r"\s*\([^)]*\)", "", diag.disease_detected).strip()
    reply_text = (
        f"🌿 *AgriPulse Crop Scan Complete* 🌿\n\n"
        f"• *Crop:* {diag.crop_name.title()}\n"
        f"• *Detected Disease:* {clean_disease}\n"
        f"• *Confidence:* {int(diag.confidence * 100)}%\n"
        f"• *Measured Leaf Damage:* {damage}% (via SAM 2)\n"
        f"• *Severity:* {severity.title()}\n\n"
        f"*{advisory.spoken_reply}*\n\n"
        f"*Step-by-step wetin you go do:*\n"
        + "\n".join(f"{i}. {s}" for i, s in enumerate(advisory.step_by_step_instructions, 1))
        + f"\n\n*Local materials you fit use:*\n"
        + "\n".join(f"• {item}" for item in advisory.local_market_substitutes)
    )
    return {"reply_text": reply_text, "crop": diag.crop_name,
            "disease": diag.disease_detected, "damage": damage,
            "language": advisory.detected_language, "spoken_reply": advisory.spoken_reply,
            "severity": severity}


async def process_incoming_whatsapp_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Parses incoming WhatsApp webhook event and generates automated agricultural response."""
    try:
        # Meta may batch entries, changes, and messages in one delivery. Do
        # not silently discard events after the first one.
        events = []
        for entry_item in payload.get("entry", []) or []:
            for change_item in entry_item.get("changes", []) or []:
                value_item = change_item.get("value", {}) or {}
                for message_item in value_item.get("messages", []) or []:
                    events.append({"object": payload.get("object"), "entry": [{
                        "id": entry_item.get("id"),
                        "changes": [{**change_item, "value": {**value_item, "messages": [message_item]}}],
                    }]})
        if len(events) > 1:
            results = [await process_incoming_whatsapp_payload(event) for event in events]
            return {"status": "processed_batch", "count": len(results), "results": results}

        entry = payload.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])

        if not messages:
            return {"status": "ignored", "reason": "no messages in payload"}

        msg = messages[0]
        sender_phone = msg.get("from", "unknown")
        msg_type = msg.get("type", "text")
        message_id = msg.get("id", "")
        if not _claim_message(message_id):
            return {"status": "ignored", "reason": "duplicate message", "message_id": message_id}

        # 1. Farmer sent a text or voice transcription
        if msg_type == "text":
            body = msg.get("text", {}).get("body", "")
            language = _message_language(body)
            clean_body = (body or "").strip().lower()

            # Friendly onboarding / greetings
            if re.match(r"^(hi|hello|hey|sannu|bawo|kedu|howdy|help|start|good (morning|afternoon|evening)|menu)\b", clean_body):
                welcome_msgs = {
                    "pidgin": (
                        "🌿 *AgriPulse Farm Doctor* 🌿\n\n"
                        "How body my friend! I be your digital farm copilot. "
                        "Snap and send me a clear photo of any sick crop leaf (Cassava, Maize, Yam, Tomato, etc.).\n\n"
                        "I go scan am, tell you the exact sickness, measure the leaf damage with SAM, and give you cheap organic medicine wey you fit prepare today!\n\n"
                        "📸 *Send leaf photo now make we start!*"
                    ),
                    "hausa": (
                        "🌿 *AgriPulse Farm Doctor* 🌿\n\n"
                        "Sannu abokina manomi! Ni ne likitan gonarka na zamani. "
                        "Dauki hoto mai kyau na ganyen amfanin gonarka da ke da ciwo ka tura min.\n\n"
                        "Zan bincika ciwon, in auna barnar da ya yi, kuma in ba ka maganin gida mai sauki a yau!\n\n"
                        "📸 *Tura hoton ganye yanzu mu fara!*"
                    ),
                    "yoruba": (
                        "🌿 *AgriPulse Farm Doctor* 🌿\n\n"
                        "Ẹ ku ojumo ore mi agbẹ! Emi ni dokita oko yin. "
                        "Ẹ ya aworan ewe to n se aisan (Gbaguda, Agbado, Isu, Tomato) ki ẹ fi ranṣẹ si mi.\n\n"
                        "Ma wo aisan na, ma wọn iye ibajẹ to wa lori ewe, ma si fun yin ni ogun ibilẹ ti ẹ le se loni!\n\n"
                        "📸 *Ẹ fi aworan ewe ranṣẹ ni bayi!*"
                    ),
                    "igbo": (
                        "🌿 *AgriPulse Farm Doctor* 🌿\n\n"
                        "Nnọọ nwanne m onye ọrụ ugbo! Abụ m dọkịta ugbo gị nke oge a. "
                        "Seta foto doro anya nke akwụkwọ ihe ubi gị na-arịa ọrịa (Akpụ, Ọka, Ji, Tọmatọ) zitere m.\n\n"
                        "Aga m enyocha ọrịa ahụ, tụọ ogo mmebi ya, ma nye gị ọgwụ ọdịnala dị ọnụ ala ị nwere ike ịkwadebe taa!\n\n"
                        "📸 *Zite foto akwụkwọ ugbu a ka anyị malite!*"
                    ),
                    "english": (
                        "🌿 *AgriPulse Farm Doctor* 🌿\n\n"
                        "Hello! I am your AI farm extension copilot. "
                        "Send me a clear photo of any diseased crop leaf (Cassava, Maize, Yam, Tomato, etc.).\n\n"
                        "I will instantly identify the disease, measure leaf damage with SAM, and provide step-by-step organic remedies and a voice note in your dialect.\n\n"
                        "📸 *Send a leaf photo now to begin!*"
                    ),
                }
                reply_text = welcome_msgs.get(language, welcome_msgs["pidgin"])
                spoken_preview = reply_text.split("📸")[0].strip()
                await send_whatsapp_text(sender_phone, reply_text)
                await send_whatsapp_voice(sender_phone, synthesize_spoken_audio(spoken_preview, language))
                return {"status": "replied", "type": "onboarding_welcome", "reply": reply_text, "language": language}

            advisory = await generate_advisory(user_query=body, language=language)

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
            await send_whatsapp_voice(sender_phone, synthesize_spoken_audio(advisory.spoken_reply, language))
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
            save_scan(
                farmer_id=f"wa-{sender_phone}", client_scan_id=message_id or None,
                crop_name=out["crop"], disease_detected=out["disease"],
                damage_percentage=float(out["damage"]), severity=out["severity"],
                language=out["language"],
            )
            await send_whatsapp_text(sender_phone, out["reply_text"])
            voice_sent = await send_whatsapp_voice(
                sender_phone, synthesize_spoken_audio(out["spoken_reply"], out["language"])
            )
            return {"status": "replied", "type": "image_diagnosis",
                    "reply": out["reply_text"], "crop": out["crop"],
                    "disease": out["disease"], "damage": out["damage"],
                    "voice_sent": voice_sent, "language": out["language"]}

        return {"status": "unsupported_type", "type": msg_type}

    except Exception as e:
        logger.error(f"Error processing WhatsApp webhook: {e}")
        return {"status": "error", "error": str(e)}
