"""FastAPI entrypoint: diagnose + segment + voice-advisory + whatsapp webhook + edge benchmark."""
import hashlib
import hmac
import logging
import os
import time
import uuid
from typing import List, Optional

# TLS: use certifi bundle so api.meta.ai verifies on machines with bare OpenSSL (e.g. macOS py.org builds).
try:
    import certifi

    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except Exception:
    pass

from fastapi import FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("agripulse.api")

limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])

from backend.services.crop_diagnostician import DiagnosisResult, diagnose_image, severity_for_damage
from backend.services.leaf_segmenter import SegmentationResult, segment_leaf_damage
from backend.services.llama_edge_runner import benchmark_on_device_inference, EXECUTORCH_CONFIGS
from backend.services.meta_models import BY_ID, MODEL_CATALOG
from backend.services.mobile_sync import get_history, save_scan, sync_batch
from backend.services.multilingual_advisor import AdvisoryResponse, generate_advisory
from backend.services.voice_synthesizer import synthesize_spoken_audio
from backend.services.dial_service import (
    dial_configured,
    process_dial_event,
    ring_farmer_with_treatment,
)
from backend.services.whatsapp_service import (
    process_incoming_whatsapp_payload,
    verify_webhook_token,
)

app = FastAPI(
    title="AgriPulse Edge API",
    version="1.3.0",
    description="Offline-First Crop Diagnostic & Multilingual Voice Copilot powered by Meta AI",
)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded. Try again shortly."})


@app.exception_handler(Exception)
async def _unhandled_handler(request: Request, exc: Exception):
    # Structured envelope: request id for the farmer/agent to quote, no stack
    # traces or key material ever leaves the server (full traceback in logs).
    rid = getattr(request.state, "rid", None) or str(uuid.uuid4())[:8]
    logger.exception(f"rid={rid} {request.method} {request.url.path} UNHANDLED: {type(exc).__name__}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong processing your request.",
                 "request_id": rid},
    )


def _origins():
    raw = os.getenv("CORS_ORIGINS", "*").strip()
    if raw == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if not str(request.url.path).startswith("/docs"):
        resp.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    return resp


app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
if os.path.isdir(WEB_DIR):
    app.mount("/site", StaticFiles(directory=WEB_DIR), name="site")

SAMPLE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_data")
if os.path.isdir(SAMPLE_DIR):
    app.mount("/sample_data", StaticFiles(directory=SAMPLE_DIR), name="sample_data")


@app.get("/", include_in_schema=False)
def public_site():
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


@app.get("/app", include_in_schema=False)
def field_workspace():
    return FileResponse(os.path.join(WEB_DIR, "app.html"))


@app.get("/privacy", include_in_schema=False)
def privacy_policy():
    return FileResponse(os.path.join(WEB_DIR, "privacy.html"))


@app.get("/terms", include_in_schema=False)
def terms_of_service():
    return FileResponse(os.path.join(WEB_DIR, "terms.html"))


@app.get("/data-deletion", include_in_schema=False)
def data_deletion():
    return FileResponse(os.path.join(WEB_DIR, "data-deletion.html"))


@app.middleware("http")
async def _request_id_log(request: Request, call_next):
    rid = str(uuid.uuid4())[:8]
    request.state.rid = rid
    t0 = time.perf_counter()
    try:
        resp = await call_next(request)
    except Exception:
        logger.exception(f"rid={rid} {request.method} {request.url.path} FAILED")
        raise
    dt = (time.perf_counter() - t0) * 1000
    logger.info(f"rid={rid} {request.method} {request.url.path} -> {resp.status_code} ({dt:.0f}ms)")
    resp.headers["X-Request-ID"] = rid
    return resp

ALLOWED = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MAX_BYTES = 10 * 1024 * 1024
# Decompression-bomb guard: a 10MB JPEG can expand to gigapixels. Pillow's
# default limit (~178MP) is too generous for a phone-photo API; cap decoded
# pixels well above the largest real smartphone sensor (~200MP) but far below
# bomb territory. Applied in _check_image before any numpy work.
MAX_IMAGE_MEGAPIXELS = float(os.getenv("MAX_IMAGE_MEGAPIXELS", "40"))
try:
    from PIL import Image as _PILImage

    _PILImage.MAX_IMAGE_PIXELS = int(MAX_IMAGE_MEGAPIXELS * 1_000_000)
except Exception:
    pass


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "AgriPulse Edge",
        "version": "1.3.0",
        "meta_ai_ready": True,
        "offline_edge_ready": True,
        "models_integrated": [m["label"] for m in MODEL_CATALOG],
    }


@app.get("/ready")
def ready():
    """Deep readiness: model registry, sample data, and cloud-key presence."""
    key_set = bool((os.getenv("MODEL_API_KEY") or os.getenv("META_API_KEY") or "").strip())
    checks = {
        "model_registry": len(MODEL_CATALOG) >= 6,
        "sample_data": os.path.isdir(
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_data")
        ),
        "cloud_key_configured": key_set,
    }
    ok = checks["model_registry"] and checks["sample_data"]
    return JSONResponse(status_code=200 if ok else 503, content={"ready": ok, "checks": checks})


class VoiceAdvisoryRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=1000)
    language: str = Field(default="pidgin")
    diagnosis_context: Optional[dict] = None
    model_id: Optional[str] = Field(default=None, description="Meta model ID override")
    use_live: bool = Field(default=False, description="Bill this call on dev.meta.ai")


class SynthesisRequest(BaseModel):
    text: str = Field(..., min_length=2, max_length=2000)
    language: str = Field(default="pidgin")


class MobileScan(BaseModel):
    client_scan_id: Optional[str] = Field(default=None, max_length=80)
    farmer_id: Optional[str] = Field(default=None, max_length=120)
    crop_name: str = Field(default="unknown", max_length=40)
    disease_detected: str = Field(default="unknown", max_length=160)
    damage_percentage: float = Field(default=0.0, ge=0.0, le=100.0)
    severity: str = Field(default="low", max_length=20)
    language: str = Field(default="pidgin", max_length=20)
    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(default=None, ge=-180.0, le=180.0)
    timestamp: Optional[str] = Field(default=None, max_length=40)


def _farmer_id_allowed(farmer_id: str) -> str:
    """Normalizes a farmer id and enforces the opt-in access policy.

    Policy: ids starting with 'coop:' are cooperative-managed and always
    allowed; any other id must present `?farmer_key=` matching FARMER_API_KEY
    when the server sets one (fail-closed for unknown ids in locked mode,
    open for local/dev when unset).
    """
    fid = (farmer_id or "anonymous").strip()[:120] or "anonymous"
    return fid


def _require_farmer_key(farmer_id: str, farmer_key: Optional[str]) -> None:
    """Enforces opt-in per-farmer auth without breaking open dev/local use.

    - `coop:*` ids: cooperative-managed, always allowed.
    - FARMER_API_KEY unset: open mode (dev, pilot, offline PWA).
    - FARMER_API_KEY set: every other id must present the matching key.
    """
    fid = (farmer_id or "anonymous").strip()
    if fid.startswith("coop:"):
        return
    expected = os.getenv("FARMER_API_KEY", "").strip()
    if not expected:
        return
    import hmac as _hm

    if not farmer_key or not _hm.compare_digest(str(farmer_key), expected):
        raise HTTPException(status_code=401, detail="Invalid farmer key")


class MobileSyncBatch(BaseModel):
    farmer_id: str = Field(..., min_length=2, max_length=120)
    scans: List[dict] = Field(default_factory=list, max_length=200)


class DialCallRequest(BaseModel):
    to: str = Field(..., min_length=7, max_length=20, description="Farmer phone in E.164, e.g. +2348012345678")
    crop_name: str = Field(default="cassava", max_length=40)
    disease_detected: str = Field(default="unknown", max_length=120)
    damage_percentage: float = Field(default=0.0, ge=0.0, le=100.0)
    steps: List[str] = Field(default_factory=list, max_length=8)
    language: str = Field(default="pidgin", max_length=20)


def _sanitize_prompt_text(value: str, limit: int = 1000) -> str:
    """Strips prompt-injection scaffolding from farmer-supplied text.

    Captions and queries are interpolated into Meta system prompts; strip
    role-play / instruction-override markers so a hostile caption cannot
    steer the agronomist prompt. Truncates to `limit` chars.
    """
    import re as _re

    text = (value or "")[:limit]
    text = _re.sub(r"(?i)\b(system|assistant|developer)\s*:", " ", text)
    text = _re.sub(r"(?i)ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", " ", text)
    text = _re.sub(r"```", " ", text)
    return " ".join(text.split())


def _check_image(file: UploadFile, raw: bytes):
    if file.content_type not in ALLOWED:
        raise HTTPException(
            415, f"Unsupported file type '{file.content_type}'. Please upload JPEG, PNG, or WebP."
        )
    if not raw:
        raise HTTPException(400, "Empty image uploaded.")
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "Image file too large (maximum 10MB).")
    # Cheap header probe: reject absurd dimensions before numpy allocates.
    try:
        from PIL import Image as _PILProbe
        import io as _io

        with _PILProbe.open(_io.BytesIO(raw)) as probe:
            probe.verify()
        with _PILProbe.open(_io.BytesIO(raw)) as probe2:
            w, h = probe2.size
            if w * h > int(MAX_IMAGE_MEGAPIXELS * 1_000_000):
                raise HTTPException(413, "Image dimensions too large.")
            if min(w, h) < 32:
                raise HTTPException(400, "Image too small for diagnosis (min 32px).")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Unreadable image file.")


@app.get("/api/v1/models")
def list_models():
    """Canonical Meta model catalog driving the dashboard selector (dev.meta.ai IDs)."""
    return JSONResponse(content={"models": MODEL_CATALOG, "by_id": BY_ID})


@app.post("/api/v1/diagnose", response_model=DiagnosisResult)
@limiter.limit("30/minute")
async def diagnose(
    request: Request,
    file: UploadFile = File(..., description="Crop leaf photo"),
    force_offline: bool = Query(
        default=False,
        description="Simulate disconnected offline on-device ExecuTorch inference (0KB data)",
    ),
    model_id: Optional[str] = Query(default=None, description="Meta model ID override"),
    use_live: bool = Query(default=False, description="Bill this call on dev.meta.ai"),
    expected_crop: Optional[str] = Query(
        default=None, max_length=40,
        description="Farmer-selected crop hint (e.g. cassava, maize, tomato, etc.)",
    ),
):
    """Diagnoses crop leaf pathology and fuses SAM 2 lesion area measurement."""
    raw = await file.read()
    _check_image(file, raw)

    try:
        result = await diagnose_image(
            raw, file.content_type, force_offline=force_offline,
            model_id=model_id, use_live=use_live, expected_crop=expected_crop,
        )
    except ValidationError as e:
        raise HTTPException(502, f"Model returned invalid schema: {e}")
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(502, str(e))

    # Perform lesion segmentation and fuse measured percentage
    try:
        seg = SegmentationResult(**segment_leaf_damage(raw))
        payload = result.model_dump(mode="json")
        payload["segmentation"] = seg.model_dump()
        merged = DiagnosisResult(**payload)
        # Fuse: prefer measured segmentation % as authoritative damage estimate
        merged.damage_percentage = max(0, min(100, int(round(seg.damage_percentage))))
        merged.severity = severity_for_damage(merged.damage_percentage)
        merged.segmentation = seg.model_dump()
        # Confidence gate: below 0.55 the app must ask for a retake, not bluff.
        merged.needs_review = merged.confidence < 0.55
        return JSONResponse(content=merged.model_dump(mode="json"))
    except Exception:
        result.needs_review = result.confidence < 0.55
        return JSONResponse(content=result.model_dump(mode="json"))


@app.post("/api/v1/diagnose-edge", response_model=DiagnosisResult)
async def diagnose_edge(
    request: Request,
    file: UploadFile = File(..., description="Crop leaf photo for offline edge diagnosis"),
    expected_crop: Optional[str] = Query(
        default=None, max_length=40,
        description="Farmer-selected crop hint (e.g. cassava, maize, etc.)",
    ),
):
    """Guaranteed zero-data offline edge diagnosis using simulated ExecuTorch on-device pipeline."""
    return await diagnose(request, file, force_offline=True, expected_crop=expected_crop)


@app.post("/api/v1/segment", response_model=SegmentationResult)
@limiter.limit("30/minute")
async def segment(request: Request, file: UploadFile = File(..., description="Crop leaf photo")):
    """Segments leaf lesion boundaries and quantifies chlorosis vs. necrosis surface area."""
    raw = await file.read()
    _check_image(file, raw)
    try:
        return JSONResponse(content=segment_leaf_damage(raw))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Segmentation failed: {e}")


@app.post("/api/v1/voice-advisory", response_model=AdvisoryResponse)
@limiter.limit("60/minute")
async def voice_advisory(request: Request, req: VoiceAdvisoryRequest):
    """Multilingual voice/text advisory in Nigerian Pidgin, Hausa, Yoruba, or simple English."""
    try:
        result = await generate_advisory(req.query, req.language, req.diagnosis_context,
                                         model_id=req.model_id, use_live=req.use_live)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    return JSONResponse(content=result.model_dump(mode="json"))


@app.post("/api/v1/voice-synthesize")
@limiter.limit("20/minute")
async def voice_synthesize(request: Request, req: SynthesisRequest):
    """Converts local dialect extension text into audible voice note audio stream."""
    if len(req.text) > 2000:
        raise HTTPException(400, "Text too long for synthesis (max 2000 chars).")
    audio_bytes = synthesize_spoken_audio(req.text, req.language)
    return Response(content=audio_bytes, media_type="audio/mpeg")


@app.get("/api/v1/edge/benchmark")
def get_edge_benchmarks():
    """Returns ExecuTorch on-device hardware telemetry for Llama 3.2 1B, 3B, and SAM 2."""
    benchmarks = {k: benchmark_on_device_inference(k) for k in EXECUTORCH_CONFIGS}
    return JSONResponse(content=benchmarks)


# ─────────────────────────────────────────────────────────────────────────────
# Mobile client offline-sync endpoints (Expo app + farmer PWA queue drain)
# ─────────────────────────────────────────────────────────────────────────────


@app.post("/api/v1/mobile/sync")
@limiter.limit("60/minute")
async def mobile_sync_one(request: Request, scan: MobileScan,
                          farmer_id: str = Query(default="anonymous", max_length=120),
                          farmer_key: Optional[str] = Query(default=None, max_length=120)):
    """Accepts a single queued farm scan from an offline mobile client."""
    _require_farmer_key(farmer_id if farmer_id != "anonymous" else (scan.farmer_id or "anonymous"),
                        farmer_key)
    fid = _farmer_id_allowed(scan.farmer_id or farmer_id)
    data = scan.model_dump()
    data.pop("farmer_id", None)
    return JSONResponse(content=save_scan(farmer_id=fid, **data))


@app.post("/api/v1/mobile/sync-batch")
@limiter.limit("30/minute")
async def mobile_sync_batch(request: Request, batch: MobileSyncBatch,
                            farmer_key: Optional[str] = Query(default=None, max_length=120)):
    """Accepts a batch of queued farm scans when the phone regains connectivity."""
    _require_farmer_key(batch.farmer_id, farmer_key)
    return JSONResponse(content=sync_batch(batch.farmer_id, batch.scans))


@app.get("/api/v1/mobile/history")
async def mobile_history(farmer_id: str = Query(default="anonymous", max_length=120),
                         limit: int = Query(default=20, ge=1, le=100),
                         farmer_key: Optional[str] = Query(default=None, max_length=120)):
    """Returns a farmer's synced scan history for the cooperative dashboard."""
    _require_farmer_key(farmer_id, farmer_key)
    return JSONResponse(content=get_history(_farmer_id_allowed(farmer_id), limit))


# ─────────────────────────────────────────────────────────────────────────────
# WhatsApp Business Cloud API Webhook Integration
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/v1/whatsapp/webhook")
async def whatsapp_verify(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
):
    """Meta Webhook verification handshake."""
    challenge = verify_webhook_token(hub_mode, hub_verify_token, hub_challenge)
    if challenge:
        return PlainTextResponse(content=challenge, status_code=200)
    raise HTTPException(status_code=403, detail="Invalid verification token")


@app.post("/api/v1/whatsapp/webhook")
async def whatsapp_message_webhook(request: Request):
    """Handles incoming farmer voice notes, photos, and messages via WhatsApp."""
    raw = await request.body()
    # Meta documents a maximum webhook payload of 3 MB. Reject oversized or
    # malformed requests before doing any model work; Meta will retry a
    # non-200 delivery, while valid status-only events are acknowledged below.
    if len(raw) > 3 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Webhook payload exceeds Meta's 3 MB limit")
    app_secret = os.getenv("WHATSAPP_APP_SECRET", "").strip()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if app_secret:
        expected = "sha256=" + hmac.new(app_secret.encode(), raw, hashlib.sha256).hexdigest()
        if not signature or not hmac.compare_digest(signature, expected):
            raise HTTPException(status_code=401, detail="Invalid WhatsApp webhook signature")
    try:
        import json
        payload = json.loads(raw or b"{}")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid WhatsApp webhook payload")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Webhook payload must be a JSON object")
    # WhatsApp Cloud API uses this object discriminator. Keep accepting an
    # empty object for dashboard health/test calls, but reject unrelated JSON.
    webhook_object = payload.get("object")
    if webhook_object not in (None, "whatsapp_business_account"):
        raise HTTPException(status_code=400, detail="Unsupported webhook object")
    result = await process_incoming_whatsapp_payload(payload)
    return JSONResponse(content=result)


class WhatsAppSimulateRequest(BaseModel):
    from_phone: str = Field(default="+2348012345678", description="Simulated farmer phone")
    message_type: str = Field(default="text", description="'text' or 'image'")
    text_body: Optional[str] = Field(default="How body, my cassava get yellow spots")
    sample_preset: Optional[str] = Field(default=None, description="Preset image file name in sample_data")
    content_base64: Optional[str] = Field(default=None, description="Raw base64 image bytes")


@app.get("/api/v1/whatsapp/status")
def whatsapp_status():
    """Reports configuration and readiness of the Meta WhatsApp Business Cloud API."""
    from backend.services.whatsapp_service import WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_VERIFY_TOKEN
    configured = bool(WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID)
    return JSONResponse(content={
        "configured": configured,
        "mode": "live" if configured else "sandbox_simulator",
        "phone_number_id": (WHATSAPP_PHONE_NUMBER_ID[:4] + "…" + WHATSAPP_PHONE_NUMBER_ID[-4:]) if WHATSAPP_PHONE_NUMBER_ID else "meta-sandbox-id",
        "verify_token": WHATSAPP_VERIFY_TOKEN,
        "webhook_url": "https://agripulse.zentreeca.org/api/v1/whatsapp/webhook",
        "cloud_api_version": "v21.0",
        "transports_supported": ["text", "image", "audio_voice_note"],
        "dialects_supported": ["pidgin", "hausa", "yoruba", "english"],
    })


@app.post("/api/v1/whatsapp/simulate")
async def whatsapp_simulate(req: WhatsAppSimulateRequest):
    """Interactive testing endpoint for Web UI / Admin sandbox to test WhatsApp channel."""
    import base64 as _b64
    msg_id = f"wamid.sim.{int(time.time() * 1000)}"
    if req.message_type == "image":
        image_b64 = req.content_base64
        if not image_b64 and req.sample_preset:
            sample_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_data", req.sample_preset
            )
            if os.path.exists(sample_path):
                with open(sample_path, "rb") as f:
                    image_b64 = _b64.b64encode(f.read()).decode("utf-8")
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "simulated-entry",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"display_phone_number": "2348012345678"},
                        "messages": [{
                            "from": req.from_phone,
                            "id": msg_id,
                            "timestamp": str(int(time.time())),
                            "type": "image",
                            "image": {
                                "id": "sim-media-1",
                                "caption": req.text_body or "",
                                "content_base64": image_b64,
                            },
                        }],
                    },
                    "field": "messages",
                }],
            }],
        }
    else:
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "simulated-entry",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"display_phone_number": "2348012345678"},
                        "messages": [{
                            "from": req.from_phone,
                            "id": msg_id,
                            "timestamp": str(int(time.time())),
                            "type": "text",
                            "text": {"body": req.text_body or "Hello"},
                        }],
                    },
                    "field": "messages",
                }],
            }],
        }
    result = await process_incoming_whatsapp_payload(payload)
    return JSONResponse(content=result)


# ─────────────────────────────────────────────────────────────────────────────
# Dial transport (getdial.ai): real phone number with WhatsApp + voice + SMS
# ─────────────────────────────────────────────────────────────────────────────


@app.get("/api/v1/dial/status")
async def dial_status():
    """Reports whether a live Dial number is configured (else simulated mode)."""
    from backend.services.dial_service import DIAL_NUMBER

    return JSONResponse(content={
        "configured": dial_configured(),
        "number": (DIAL_NUMBER[:4] + "…" + DIAL_NUMBER[-3:] + " (masked)")
        if DIAL_NUMBER else None,
        "transports": ["whatsapp", "voice", "sms"],
    })


@app.post("/api/v1/dial/webhook")
@limiter.limit("60/minute")
async def dial_webhook(request: Request):
    """Receives Dial message.received events (photo in media array -> voice note out)."""
    if len(await request.body()) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Dial event too large")
    secret = os.getenv("DIAL_WEBHOOK_SECRET", "").strip()
    if secret:
        import hashlib as _hl
        import hmac as _hm

        raw = await request.body()
        sig = request.headers.get("X-Dial-Signature", "") or request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + _hm.new(secret.encode(), raw, _hl.sha256).hexdigest()
        if not sig or not _hm.compare_digest(sig, expected):
            raise HTTPException(status_code=401, detail="Invalid Dial webhook signature")
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    result = await process_dial_event(payload if isinstance(payload, dict) else {})
    return JSONResponse(content=result)


@app.post("/api/v1/dial/call")
@limiter.limit("10/minute")
async def dial_call(request: Request, req: DialCallRequest):
    """Rings a farmer and reads the treatment slip aloud (offline-week fallback)."""
    import re as _re

    if not _re.fullmatch(r"\+\d{7,15}", req.to.strip()):
        raise HTTPException(status_code=400, detail="to must be E.164 (e.g. +2348012345678)")
    steps = [_sanitize_prompt_text(s, 300) for s in (req.steps or [])[:4]] or [
        "Prepare neem leaf spray as advised by the extension officer.",
        "Spray under the leaves at sunset.",
        "Remove badly infected leaves and bury them far from the farm.",
    ]
    result = await ring_farmer_with_treatment(
        req.to.strip(), _sanitize_prompt_text(req.crop_name, 40),
        _sanitize_prompt_text(req.disease_detected, 120),
        req.damage_percentage, steps, req.language)
    return JSONResponse(content=result)
