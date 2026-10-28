# Competition strategy

The official hackathon page says Indie projects are judged on **creativity, technical ambition, and whether they work**. Startup projects are judged on **technical execution and whether the product holds up in production**. Present AgriPulse as a working last-mile agricultural intelligence system, not a list of model integrations.

## Winning thesis

**The differentiator is the delivery architecture:** the same grounded crop diagnosis becomes an extension-worker workflow, a reconnect-safe mobile record, and a WhatsApp voice response for a farmer.

## What judges must see

1. A real input producing a real structured diagnosis.
2. Visible Meta participation: `model_used`, `live_call`, segmentation method, and usage metadata when available.
3. Cross-channel consistency: crop, damage, severity, and guidance cannot contradict each other.
4. Failure behavior: non-leaf rejection, low-confidence review, cloud fallback, and webhook deduplication.
5. A clear boundary between working implementation and future edge deployment.

## Priorities before submission

### P0 — must demonstrate

- Configure `MODEL_API_KEY` and capture one successful Muse Image, Muse reasoning, and SAM 3.1 run.
- Configure a Meta WhatsApp test number plus `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`, and `WHATSAPP_APP_SECRET`.
- Replace `CORS_ORIGINS=*` with the deployed domain.
- Run the full test matrix and record the output for the demo video.
- Use the same two reference images in web and WhatsApp to prove parity.

### P1 — strongest technical upgrade

- Ship a real ExecuTorch `.pte` model through a mobile native module, or keep the reconnect-queue claim. Never demo a server endpoint as on-device inference.
- Replace process-local WhatsApp deduplication with durable event storage for multi-instance deployment.
- Move SQLite records to managed Postgres for multi-instance production.
- Add authenticated cooperative tenancy before handling real farmer data.

### P2 — pilot readiness

- Validate remedy content with a named extension or agronomy partner.
- Add consent, retention, and deletion controls for farmer phone numbers and location.
- Establish a labeled field benchmark with per-crop precision, recall, and abstention rate.

## Demo rules

- Lead with the farmer outcome, then reveal technical depth.
- Show one coherent journey; do not tour every tab.
- Never quote synthetic benchmark numbers as device measurements.
- Label local fallbacks clearly. Resilience is a strength when presented honestly.
- End with evidence: WhatsApp response, cooperative record, and green tests.
