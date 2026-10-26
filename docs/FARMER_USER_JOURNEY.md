# AgriPulse Edge — Farmer User Journey 👩🏾‍🌾

2-tap, zero-jargon path for a low-literacy smallholder (works with zero cellular data).

## The 2-tap journey
1. **Tap 1 — Snap/Upload leaf** (`📸 CHECK MY LEAF` in PWA, `📸 Snap Sick Leaf` in Expo app).
   On-device edge model (`/api/v1/diagnose-edge`) identifies crop by leaf shape, fuses SAM 2 lesion %.
2. **Tap 2 — Auto-play voice note** in the farmer's dialect (Pidgin / Hausa / Yoruba).
   Backend: `/api/v1/voice-advisory` → `/api/v1/voice-synthesize` (MP3 voice note).
3. **Do the 3 cheap things** — Neem 🌿 / Ash 🪵 / Soap 🧼 recipe cards with numbered steps.
4. **Save offline** — stored on-device; auto-syncs to the cooperative when network returns
   (`POST /api/v1/mobile/sync-batch`, history at `GET /api/v1/mobile/history`).

## Who does what (3-tier architecture)
| Tier | Channel | User | Needs |
| :--- | :--- | :--- | :--- |
| 1. Farmer | WhatsApp voice/photo (`/api/v1/whatsapp/webhook`) | Mama Nkechi, no smartphone literacy | Zero app install, dialect voice notes |
| 2. Extension agent | Mobile app (`mobile/`) + PWA (`frontend/mobile_farmer.py`) | Youth agripreneur with Android | Offline camera, 360px big buttons, auto-sync |
| 3. Cooperative | Web dashboard (`frontend/app.py`) | Coop manager with laptop | Outbreak map, SAM 2 masks, benchmark telemetry |

## Language map
- Pidgin (default): "How I go prepare neem spray?" → playful, direct steps.
- Hausa: "Yaya zan hada maganin neem?" → respectful northern phrasing.
- Yoruba: "Bawo ni mo se lo ewe neem?" → respectful southwestern phrasing.
- English: simple plain words, no academic jargon.

## Offline guarantees
- Diagnosis + segmentation + advisory templates + history all work with **0 KB** data.
- Every scan carries `client_scan_id`; sync is idempotent — re-sending never duplicates.
- Queue survives app restarts (AsyncStorage on device, `SYNC_STORE` server-side demo).
