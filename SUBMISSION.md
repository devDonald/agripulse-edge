# AgriPulse Edge 🌿 — Hackathon Submission

> **For the Cerebral Valley / Devpost form** — copy each section into the matching field.

## Project Title
**AgriPulse Edge — Offline-First AI Crop Doctor & Multilingual Voice Copilot for African Smallholders**

## Tagline
Snap a sick leaf with zero data — hear the cure in Pidgin, Hausa, or Yoruba. Llama 3.2 Vision + SAM 2 + ExecuTorch, in the farmer's pocket.

## Category
**Build for Your World** (Agriculture & Food Security)

## Inspiration
80% of Sub-Saharan food comes from smallholders losing up to 40% of yields to Fall Armyworm,
Cassava Mosaic, and Blight. Cloud-only AI fails them twice: rural farms have zero/sporadic data,
and extension manuals are academic English. We met "Mama Nkechi" — literate in farming, not in
English PDFs. AgriPulse Edge meets her where she is: camera, voice, WhatsApp — offline first.

## What it does (3-Tier Architecture)
| Tier | Channel | User | Experience |
| :--- | :--- | :--- | :--- |
| 1. Farmer | WhatsApp voice/photo (`POST /api/v1/whatsapp/webhook`) | Low-literacy farmer | Zero install; dialect voice-note diagnosis + neem/ash recipes |
| 2. Extension | Expo mobile app (`mobile/`) + PWA (`frontend/mobile_farmer.py` :8502) | Youth agripreneur w/ Android | Giant Snap button, offline queue, auto-sync to `/api/v1/mobile/sync-batch` |
| 3. Cooperative | Web dashboard (`frontend/app.py` :8501) | Coop manager w/ laptop | SAM 2 lesion maps, outbreak history (`GET /api/v1/mobile/history`), NPU telemetry |

2-tap journey: **Snap Sick Leaf → Play Voice Advice**. Crop identified by leaf *shape* (never
maize-as-cassava), damage measured by SAM 2, cure spoken in dialect with 3 organic recipe cards.

## The Meta AI Stack Used
- **Llama 3.2 90B Vision** (Meta Model API) — cloud pathology diagnosis + symptom reasoning.
- **Llama 3.2 3B / 1B via ExecuTorch (INT8/INT4)** — on-device zero-data inference (0 KB, ~38 ms,
  `/api/v1/diagnose-edge`, live NPU benchmark at `/api/v1/edge/benchmark`).
- **Segment Anything 2 (SAM 2)** — pixel-accurate chlorosis/necrosis masks + damage % (`/api/v1/segment`).
- **WhatsApp Business Cloud API** — webhook verify + inbound text/image dispatch in Pidgin.

## How to run (judges, 60 seconds)
```bash
git clone <repo> && cd agri-diagnose-backend
pip install -r requirements.txt
bash scripts/start_all.sh
# Backend:   http://localhost:8000/docs
# Dashboard: http://localhost:8501
# Farmer PWA: http://localhost:8502
```

## 2-Minute Demo Video Script
| Time | Shot | Script |
| :--- | :--- | :--- |
| 0:00–0:25 | Problem montage (field, no-signal icon, English manual) | "Smallholders lose 40% of crops. No data, no English — cloud AI never reaches them." |
| 0:25–0:55 | Dashboard :8501 → ✈️ Offline Edge → 🍃 Cassava preset → Diagnose | "Airplane mode. One tap. Instant diagnosis with 0KB data — measured 45% damage." |
| 0:55–1:20 | SAM 2 opacity slider (yellow/red mask) | "SAM 2 maps every lesion pixel — yellow chlorosis, red necrosis. No guessing." |
| 1:20–1:45 | Voice Copilot → Pidgin → ▶️ Play (audio audible) | "And she hears the cure in her own tongue — neem spray, ash, soap." |
| 1:45–2:00 | Farmer PWA :8502 on phone + WhatsApp sim + Edge telemetry | "Phone, WhatsApp, or coop dashboard — same brain. Built for her world. 🌿" |

## Tests & proof
- `python3 -m pytest tests/test_robustness.py` → 18/18 passing (incl. maize-never-cassava shape tests).
- `MOCK_MODE=true python3 scripts/test_mobile_sync.py` → ALL PASS (edge + voice + audio + sync batch + history).
- `bash scripts/start_all.sh --test` → all 3 services boot cleanly.
