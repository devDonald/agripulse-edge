# AgriPulse Edge 🌿
### Offline-First Crop Diagnostic & Multilingual Voice Copilot for Smallholder Farmers
> **Built for the Meta Global AI Developer Hackathon 2026**  
> **Track:** *Build for Your World / Agriculture & Food Security*  
> **Core Tech:** Meta Model API (Muse Image + Muse Spark/Wonder), SAM 3.1, Meta WhatsApp Business Cloud API, and a reconnect-safe Expo field client.

> **Implementation boundary:** the web/API pipeline has a local edge-profile fallback and ExecuTorch benchmark harness. The current Expo client captures and queues photos offline, then diagnoses and syncs them after reconnection. It does not yet ship a native `.pte` runtime; see [`docs/COMPETITION_STRATEGY.md`](docs/COMPETITION_STRATEGY.md).

---

## 🌍 The Real-World Problem
In Sub-Saharan and West Africa, over 80% of staple food production relies on smallholder farmers. These communities lose up to **40% of their crop yields** annually to destructive pests (Fall Armyworm) and foliar diseases (Cassava Mosaic, Early Blight, Southern Corn Rust).

Most AI agricultural tools fail in the field due to two hard realities:
1. **The Connectivity Divide:** Rural farms operate with expensive, spotty, or zero cellular data. Cloud-only AI tools fail in the field.
2. **The Language & Literacy Divide:** Technical extension manuals are written in academic English, ignoring indigenous languages and everyday spoken dialects like **Nigerian Pidgin**, **Hausa**, and **Yoruba**.

---

## 🚀 The AgriPulse Solution: An Edge-Cloud Hybrid

```
                      ┌─────────────────────────────────────────┐
                      │          Smallholder Farmer             │
                      └──────────────┬──────────────────────────┘
                                     │
                     ┌───────────────┴───────────────┐
                     ▼                               ▼
       [In Field: Zero Cellular Data]     [In Village: Cell Coverage]
       📥 Offline Capture + Queue          🌐 Online WhatsApp & Web Mode
                     │                               │
       ┌─────────────▼─────────────┐     ┌───────────▼─────────────┐
       │  Expo Persistent Queue    │     │   Meta Model API Cloud  │
       │  • Keeps local photo URI  │     │ Muse Image + Reasoning  │
       │  • Auto-runs on reconnect │     │ + SAM 3.1 Mask Engine   │
       │  • Idempotent batch sync  │     │ + WhatsApp Text/Audio   │
       │  • No lost field capture  │     │ • Shared Record Stream  │
       │   • 142 MB Peak RAM       │     │ • Organic Remedies DB   │
       └─────────────┬─────────────┘     └───────────┬─────────────┘
                     │                               │
                     └───────────────┬───────────────┘
                                     ▼
                     ┌───────────────────────────────┐
                     │   Verified Farm Diagnosis     │
                     │   • Measured Lesion Area %    │
                     │   • Pidgin/Hausa Spoken Voice │
                     │   • Zero-Cost Organic Recipe  │
                     └───────────────────────────────┘
```

---

## 🛠️ The Meta AI Model Matrix

| Model / Technology | Deployment Tier | Purpose in AgriPulse Edge | Key Advantage |
| :--- | :--- | :--- | :--- |
| **Muse Image + Muse Spark/Wonder** | Meta Model API | Pixel-grounded diagnosis plus structured pathology reasoning | Current hackathon model family with visible usage metadata |
| **Local crop-shape gate** | API edge profile | Rejects non-leaf inputs and guards against crop hallucination | Deterministic fallback and paid-call gate |
| **SAM 3.1** | Meta Model API | Lesion segmentation and damage quantification | Falls back to a clearly labelled local spatial mask |
| **Meta WhatsApp Business API** | Conversational Channel | Automated messaging, leaf image diagnosis, and dialect voice notes | No app installation needed; 100% familiar interface |

---

## 📱 3-Tier Architecture (Farmer → Extension → Cooperative)

| Tier | Channel | Target User | Capabilities |
| :--- | :--- | :--- | :--- |
| **1. Farmer** | WhatsApp (`/api/v1/whatsapp/webhook`) | Rural smallholder, low literacy | Dialect voice notes, zero app install, photo leaf diagnosis |
| **2. Extension Worker** | Mobile App (`mobile/`) & PWA (`frontend/mobile_farmer.py`) | Field extension agent w/ phone | Offline camera, 1-tap presets, 3-step progress pulse, local scan history |
| **3. Cooperative** | Web Dashboard (`frontend/app.py`) | Coop manager w/ laptop | Model comparison, SAM 2 EXIF-aware opacity slider, treatment slips, telemetry |

Full field walkthrough: [`docs/FARMER_USER_JOURNEY.md`](docs/FARMER_USER_JOURNEY.md).

---

## ⚡ Quickstart & Running Locally

### 1. Prerequisites & Installation
```bash
# Clone repository
git clone https://github.com/devDonald/agripulse-edge.git
cd agripulse-edge

# Install dependencies (Python 3.10+)
pip install -r requirements.txt

# Configure environment (works out of the box with MOCK_MODE=true)
cp .env.example .env
```

### 2. One-Click Full Stack Launcher
Start all 3 services together (Backend :8000, Dashboard :8501, Farmer PWA :8502):
```bash
bash scripts/start_all.sh
```

### New unified product experience

The FastAPI service now ships the production-facing website and role-aware workspace directly:

- **Public website:** `http://localhost:8000/` — product story, user journeys, and Meta AI architecture.
- **Field workspace:** `http://localhost:8000/app` — responsive crop clinic for extension teams.
- **Cooperative command center:** `http://localhost:8000/app?mode=command` — operational overview.
- **API documentation:** `http://localhost:8000/docs` — integration and judge verification.

The crop clinic is connected to the existing diagnosis, SAM lesion analysis, multilingual advisory,
voice synthesis, mobile history, and model catalog endpoints. The `web/` directory is framework-free,
so the same Render service deploys the API and experience without a separate frontend build pipeline.

Or run services individually:

#### Backend API (FastAPI)
```bash
python3 -m uvicorn backend.main:app --reload --port 8000
```
Interactive Swagger docs: `http://localhost:8000/docs`

#### Cooperative Web Dashboard
```bash
streamlit run frontend/app.py --server.port 8501
```
Open **`http://localhost:8501`** in your browser.

#### Farmer Mobile PWA (High-Contrast, Touch-Optimized)
```bash
streamlit run frontend/mobile_farmer.py --server.port 8502
```
Open **`http://localhost:8502`** on mobile or desktop.

### 3. Expo Mobile App (React Native / Offline Sync)
```bash
cd mobile
npm install
npx expo start
```
Features:
- Giant `📸 Snap Sick Leaf` button with live camera preview.
- Language pills (Pidgin, Hausa, Yoruba, English).
- Tap-to-configure LAN IP setting for seamless field connectivity.
- Offline queue (`AsyncStorage`) that auto-drains to `POST /api/v1/mobile/sync-batch`.

---

## 🐳 Docker Deployment

Build and run the production backend with Docker:
```bash
# Build container image
docker build -t agripulse-edge:latest .

# Run container
docker run -p 8000:8000 --env-file .env agripulse-edge:latest
```

---

## 🛡️ Production Hardening & Innovations

- **Visual Grounding & Morphological Blade-Priority Classifier:**
  - Robust shape-prior classifier preventing false positives (e.g., maize vs. cassava leaf geometry).
  - High-confidence distinction between Southern Corn Rust and Gray Leaf Spot (GLS).
  - Proven **44/44 orientation stability** across leaf rotations, flips, and varying angles.
- **Idempotent SQLite Sync Store:**
  - `POST /api/v1/mobile/sync-batch` processes offline field scans with client-generated IDs (`client_scan_id`).
  - SQLite WAL mode ensures non-blocking concurrent writes with zero duplicate entries.
- **Production API Reliability:**
  - Built-in rate limiting via `slowapi` (`30/min` on diagnosis, `20/min` on voice synthesis).
  - Correlation request IDs (`rid=...`) on all endpoints for end-to-end auditability.
  - EXIF orientation auto-transpose (`ImageOps.exif_transpose`) ensuring zero distortion on real smartphone photos.
- **Extension Officer Treatment Slip Export:**
  - 1-click export of structured treatment slips (plain text/markdown) ready for SMS or print distribution to farmers.

---

## 📞 Dial Transport (getdial.ai) — Real Number, WhatsApp + Voice + SMS

For demo + pilot: a real Dial phone number replaces the simulated WhatsApp
path. Farmer sends a leaf photo → `message.received` media array → diagnose →
Pidgin/Hausa voice note back. Offline that week? Same number rings them and
reads the treatment slip aloud. No data needed on their side.

```bash
npm i -g @getdial/cli && dial auth login you@example.com
# provision a number, then point its webhook at https://YOUR_HOST/api/v1/dial/webhook
MOCK_MODE=true python3 scripts/test_dial_transport.py   # simulated mode, no key needed
```

| Endpoint | Purpose |
| :--- | :--- |
| `GET /api/v1/dial/status` | Live-number check (masked) vs simulated mode |
| `POST /api/v1/dial/webhook` | `message.received` → diagnosis + voice-note reply |
| `POST /api/v1/dial/call` | Outbound treatment readout call |

Env: `DIAL_API_KEY`, `DIAL_NUMBER`, `DIAL_WEBHOOK_SECRET` (see `.env.example`).
The Meta WhatsApp Cloud webhook stays live alongside — belt and suspenders.

---

## 🧪 Comprehensive Test Suite

### Automated Robustness Tests (19/19 Passing)
```bash
MOCK_MODE=true python3 -m pytest tests/test_robustness.py -v
```

Tests cover:
- `test_health_check` — Synchronized catalog and readiness verification.
- `test_diagnose_cassava_mosaic` — Cassava Mosaic pathology detection & remedies.
- `test_diagnose_maize_fall_armyworm` — Armyworm chewing damage detection.
- `test_diagnose_tomato_early_blight` — Concentric target-board spot detection.
- `test_diagnose_healthy_leaf` — High-vigor leaf verification.
- `test_diagnose_edge_zero_data` — Zero-data ExecuTorch telemetry validation.
- `test_reject_non_leaf_image` — Non-vegetative input rejection.
- `test_segment_endpoint` — SAM 2 lesion area measurement.
- `test_multilingual_voice_advisory_pidgin/hausa/yoruba` — Multi-dialect copilot accuracy.
- `test_voice_synthesize_endpoint` — Audible voice note stream generation.
- `test_whatsapp_webhook_verification` — Meta webhook challenge handshake.
- `test_whatsapp_webhook_incoming_message` — Inbound WhatsApp dispatch.
- `test_edge_benchmark_endpoint` — ExecuTorch hardware metrics.

### Stability Matrix & Offline Sync Verification
```bash
# 44/44 rotation and crop stability verification
python3 scripts/test_stability_matrix.py

# Idempotent batch sync and history test
python3 scripts/test_mobile_sync.py
```

---

## 📊 Live ExecuTorch Edge Hardware Benchmark
Run the standalone hardware benchmark script:
```bash
PYTHONPATH=. python3 scripts/benchmark_executorch_llama32.py
```

Output:
```
🔹 Model: Meta Llama-3.2-1B-Instruct (ExecuTorch Edge)
   • Parameter Count:       1.23 Billion
   • Quantization:          INT4 Weight-Only (AWQ) + FP16 Activations
   • Cellular Data Used:    0 KB (100% Offline)
   • Generation Throughput: 24.5 tokens/sec
   • Time-to-First-Token:   61.2 ms
--------------------------------------------------------------------------------
🔹 Model: Meta Llama-3.2-3B-Instruct (ExecuTorch Edge)
   • Parameter Count:       3.21 Billion
   • Quantization:          INT8 Weight-Only (Per-Channel)
   • Peak RAM Footprint:    1840.0 MB
   • Cellular Data Used:    0 KB (100% Offline)
   • Time-to-First-Token:   89.3 ms
--------------------------------------------------------------------------------
🔹 Model: Meta Segment Anything 2 (SAM 2 Hiera Tiny)
   • Frame Latency:         45.0 ms per frame
   • Cellular Data Used:    0 KB (100% Offline)
```

---

## 📄 License
This project is open-source under the [MIT License](LICENSE).
