# AgriPulse Edge — Hackathon Submission

## One-line pitch

AgriPulse turns one crop photo into a measured diagnosis and spoken field action, delivered through web, mobile, or WhatsApp in Pidgin, Hausa, Yoruba, and simple English.

## Track and theme

- **Recommended track:** Startup if the team intends to continue as a product; Indie only if submitting as an individual.
- **Theme:** Build for Your World.
- **Why it fits:** It applies Meta’s newest image, reasoning, segmentation, and messaging capabilities to crop protection in low-connectivity communities.

## What works in the submitted build

1. A farmer or extension officer submits one leaf photo through web, Expo mobile, or WhatsApp.
2. A local visual gate rejects non-leaf photos and provides a morphological crop-shape guard (covering 11 staple crops) before paid inference.
3. Muse Image is attempted for pixel-grounded diagnosis when Meta Model API credentials are configured. Muse reasoning refines pathology while the crop guard prevents cross-crop hallucinations.
4. SAM 3.1 is attempted for lesion segmentation; a deterministic spatial-mask fallback keeps the demo functional if the remote model is unavailable.
5. One severity policy converts measured damage into low, moderate, or severe across every channel.
6. The response includes three practical, low-cost organic actions and spoken guidance in four languages (Pidgin, Hausa, Yoruba, English).
7. Web, mobile, and WhatsApp cases enter one idempotent cooperative record stream.

## Crop & Pathology Coverage (11 Crops, ~30 Pathologies)

Full morphological prior classification and localized 3-step organic remedy protocols are implemented for:
- **Cassava:** Cassava Mosaic Disease (CMD), Cassava Bacterial Blight (CBB), Cassava Brown Streak (CBSD), Healthy Leaf
- **Maize:** Fall Armyworm (*Spodoptera frugiperda*), Common / Southern Rust (*Puccinia*), Gray Leaf Spot (GLS), Maize Streak Virus (MSV), Northern Leaf Blight, Healthy Blade
- **Tomato:** Early Blight (*Alternaria solani*), Late Blight (*Phytophthora infestans*), Yellow Leaf Curl (TYLCV), Septoria, Healthy Leaf
- **Yam:** Yam Anthracnose (*Colletotrichum gloeosporioides*), Yam Mosaic Virus (YMV), Healthy Leaf
- **Cowpea:** Cowpea Aphids (*Aphis craccivora*), Cowpea Yellow Mosaic Virus (CYMV), Healthy Leaf
- **Sorghum:** Sorghum Anthracnose (*Colletotrichum sublineolum*), Sorghum Leaf Blight, Covered Smut, Healthy Blade
- **Rice:** Rice Blast (*Magnaporthe oryzae*), Bacterial Leaf Blight (*Xanthomonas oryzae*), Healthy Ribbon
- **Pepper:** Bacterial Leaf Spot (*Xanthomonas campestris*), Pepper Mosaic Virus (PepMV), Healthy Leaf
- **Okra:** Okra Yellow Vein Mosaic Virus (OYVMV), Okra Powdery Mildew, Healthy Leaf
- **Groundnut:** Groundnut Rosette Virus (GRV), Early Leaf Spot (*Cercospora arachidicola*), Healthy Leaf
- **Sweet Potato:** Sweet Potato Virus Disease (SPVD), Alternaria Leaf Spot, Healthy Leaf
- **Vegetative Gate:** Rejection of non-leaf photos (bare ground, hands, walls) before cloud invocation.

## Channel behavior

| Channel | Primary user | Demonstrated behavior |
| --- | --- | --- |
| Web clinic | Extension officer | Upload, diagnosis, lesion overlay, severity, remedies, voice playback, saved record |
| Expo mobile | Field worker | Camera capture, online diagnosis, offline photo queue, automatic diagnosis and sync after reconnection |
| WhatsApp | Farmer | Photo download, diagnosis, text response, language-aware voice audio, signed webhook, retry deduplication |
| Command center | Cooperative lead | Operational overview, synced field records, and model status |

## Meta technology used

- **Muse Image:** pixel-grounded visual diagnosis when configured.
- **Muse Spark/Wonder:** pathology reasoning and structured multilingual extension guidance.
- **SAM 3.1:** lesion segmentation and damage quantification when configured.
- **WhatsApp Business Cloud API:** zero-install image intake and audio response.
- **Edge path:** a measurable local crop gate and benchmark harness. The Expo build queues photos offline and diagnoses them on reconnect; do not claim it runs ExecuTorch locally until a `.pte` runtime is shipped on the phone.

## Production Hardening & Reliability Evidence

- **SSRF Defense:** Meta Graph downloads allowlisted exclusively to Meta CDN domains (`lookaside.fbsbx.com`, `scontent.xx.fbcdn.net`, `.fbcdn.net`) with HTTPS streaming and 10MB caps; Dial media fetch blocks RFC 1918, link-local (169.254.x.x), loopback, and local files.
- **Image Decompression Bomb Defense:** Enforced `PIL.Image.MAX_IMAGE_PIXELS = 40_000_000` (40 Megapixels max) and early header probing to reject oversized dimensions before allocation.
- **Dual-Mode Cooperative Tenancy & Auth:** Cooperative IDs (`coop:*`) always pass; configurable `FARMER_API_KEY` with timing-safe comparison (`hmac.compare_digest`) locks down endpoints in production while supporting open local development.
- **Strict Payload & Field Caps:** Length and value validation on all Pydantic schemas (text <= 2,000 chars, query <= 1,000 chars, batch <= 200 items, lat/lon bounds, damage 0-100%, E.164 phone formatting).
- **Prompt Injection Defense:** `_sanitize_prompt_text` eliminates instruction overrides and system hijacking attempts from farmer captions before LLM reasoning.
- **Cryptographic Signatures:** Full HMAC-SHA256 signature verification for WhatsApp (`X-Hub-Signature-256`) and Dial (`X-Dial-Signature`).
- **Idempotency & Deduplication:** Webhook deduplication (`_claim_message`) and SQLite WAL unique-constraint synchronization prevent duplicate entries on retry.
- **Defensive Headers & Traceback Masking:** Standard security headers (HSTS, nosniff, frame-ancestors none), unique request correlation IDs (`X-Request-ID`), and sanitized 500 error envelopes without internal stack trace leakage.
- **Comprehensive 41/41 Automated Test Suite:**
  - `tests/test_robustness.py` (21 tests) — full integration, healthy leaf, 8 new crops, multilingual voice, zero-data edge.
  - `tests/test_security.py` (16 tests) — SSRF prevention, image bomb rejection, farmer key auth, webhook signatures, injection scrubbing, field caps.
  - `tests/test_channel_contracts.py` (4 tests) — cross-channel parity between Web, Mobile, and WhatsApp.
  - `scripts/test_stability_matrix.py` (124 runs) — 11 crops under 11 visual distortions.
  - `scripts/test_mobile_sync.py` — SQLite WAL batch queue and sync store idempotency.

## Two-minute judging demo

| Time | Show | Judge takeaway |
| --- | --- | --- |
| 0:00–0:20 | Farmer problem and three-channel architecture | This is a last-mile product, not a classifier demo. |
| 0:20–0:50 | Upload the bundled maize or cassava image in `/app` | The core diagnosis works live. |
| 0:50–1:10 | Show lesion overlay, measured damage, engine label, and matching severity | The output is explainable and consistent. |
| 1:10–1:30 | Play Pidgin, Hausa, or Yoruba guidance | Model output becomes accessible action. |
| 1:30–1:50 | Send the same image through WhatsApp and show text plus voice | One intelligence layer reaches a familiar channel. |
| 1:50–2:00 | Show the saved record and green contract tests | The prototype holds together as a system. |

## Honest boundary

AgriPulse is decision support, not a replacement for laboratory confirmation or a qualified agronomist. Low-confidence scans ask for a retake or expert review. Treatment guidance should be validated with local extension partners before broad deployment.
