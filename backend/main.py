"""FastAPI entrypoint: diagnose + segment + voice-advisory + whatsapp webhook + edge benchmark."""
import logging
import os
import time
import uuid
from typing import Optional

# TLS: use certifi bundle so api.meta.ai verifies on machines with bare OpenSSL (e.g. macOS py.org builds).
try:
    import certifi

    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except Exception:
    pass

from fastapi import FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response
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

from backend.services.crop_diagnostician import DiagnosisResult, diagnose_image
from backend.services.leaf_segmenter import SegmentationResult, segment_leaf_damage
from backend.services.llama_edge_runner import benchmark_on_device_inference, EXECUTORCH_CONFIGS
from backend.services.meta_models import BY_ID, MODEL_CATALOG
from backend.services.mobile_sync import get_history, save_scan, sync_batch
from backend.services.multilingual_advisor import AdvisoryResponse, generate_advisory
from backend.services.voice_synthesizer import synthesize_spoken_audio
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


def _origins():
    raw = os.getenv("CORS_ORIGINS", "*").strip()
    if raw == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _request_id_log(request: Request, call_next):
    rid = str(uuid.uuid4())[:8]
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
    query: str = Field(..., min_length=2)
    language: str = Field(default="pidgin")
    diagnosis_context: Optional[dict] = None
    model_id: Optional[str] = Field(default=None, description="Meta model ID override")
    use_live: bool = Field(default=False, description="Bill this call on dev.meta.ai")


class SynthesisRequest(BaseModel):
    text: str = Field(..., min_length=2)
    language: str = Field(default="pidgin")


class MobileScan(BaseModel):
    client_scan_id: Optional[str] = None
    farmer_id: Optional[str] = None
    crop_name: str = "unknown"
    disease_detected: str = "unknown"
    damage_percentage: float = 0.0
    severity: str = "low"
    language: str = "pidgin"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timestamp: Optional[str] = None


class MobileSyncBatch(BaseModel):
    farmer_id: str = Field(..., min_length=2)
    scans: list = Field(default_factory=list)


def _check_image(file: UploadFile, raw: bytes):
    if file.content_type not in ALLOWED:
        raise HTTPException(
            415, f"Unsupported file type '{file.content_type}'. Please upload JPEG, PNG, or WebP."
        )
    if not raw:
        raise HTTPException(400, "Empty image uploaded.")
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "Image file too large (maximum 10MB).")


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
):
    """Diagnoses crop leaf pathology and fuses SAM 2 lesion area measurement."""
    raw = await file.read()
    _check_image(file, raw)

    try:
        result = await diagnose_image(raw, file.content_type, force_offline=force_offline,
                                      model_id=model_id, use_live=use_live)
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
        merged.segmentation = seg.model_dump()
        return JSONResponse(content=merged.model_dump(mode="json"))
    except Exception:
        return JSONResponse(content=result.model_dump(mode="json"))


@app.post("/api/v1/diagnose-edge", response_model=DiagnosisResult)
async def diagnose_edge(
    request: Request,
    file: UploadFile = File(..., description="Crop leaf photo for offline edge diagnosis"),
):
    """Guaranteed zero-data offline edge diagnosis using simulated ExecuTorch on-device pipeline."""
    return await diagnose(request, file, force_offline=True)


@app.post("/api/v1/segment", response_model=SegmentationResult)
async def segment(file: UploadFile = File(..., description="Crop leaf photo")):
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
async def voice_advisory(req: VoiceAdvisoryRequest):
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
async def voice_synthesize(req: SynthesisRequest):
    """Converts local dialect extension text into audible voice note audio stream."""
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
async def mobile_sync_one(scan: MobileScan, farmer_id: str = Query(default="anonymous")):
    """Accepts a single queued farm scan from an offline mobile client."""
    fid = scan.farmer_id or farmer_id
    data = scan.model_dump()
    data.pop("farmer_id", None)
    return JSONResponse(content=save_scan(farmer_id=fid, **data))


@app.post("/api/v1/mobile/sync-batch")
async def mobile_sync_batch(batch: MobileSyncBatch):
    """Accepts a batch of queued farm scans when the phone regains connectivity."""
    return JSONResponse(content=sync_batch(batch.farmer_id, batch.scans))


@app.get("/api/v1/mobile/history")
async def mobile_history(farmer_id: str = Query(default="anonymous"), limit: int = Query(default=20, ge=1, le=100)):
    """Returns a farmer's synced scan history for the cooperative dashboard."""
    return JSONResponse(content=get_history(farmer_id, limit))


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
    payload = await request.json()
    result = await process_incoming_whatsapp_payload(payload)
    return JSONResponse(content=result)
