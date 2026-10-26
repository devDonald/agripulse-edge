# AgriPulse Edge — Farmer Mobile Client 📱🌿

Ultra-simple, offline-first React Native / Expo app for smallholder farmers.
2-tap journey: **Snap Sick Leaf → Hear Voice Advice**. No jargon, no typing.

## Screens
1. **Camera / Home** — giant `📸 Snap Sick Leaf` button, `⚡ 100% Offline Mode (0KB Data Used)` pill,
   language pills (Pidgin / Hausa / Yoruba), gallery fallback.
2. **Instant Diagnosis & Audio** — big disease icon + simple name, `🔊 Play Voice Advice` button,
   3 visual recipe cards (Neem / Ash / Soap), `💾 Save to Offline History`.

## Network sync
- Diagnosis runs **on-device first** (bundled edge model stub → falls back to queued server sync).
- `expo-network` watches connectivity; when online, `offlineQueue.js` auto-pushes queued scans to
  `POST /api/v1/mobile/sync-batch` and marks them synced in AsyncStorage. Zero farmer action needed.

## Configure backend
```js
// src/api.js
export const BACKEND_URL = 'http://YOUR_LAPTOP_IP:8000'; // phone + laptop on same Wi-Fi
```

## Run
```bash
cd mobile
npm install
npx expo start
# scan the QR code with Expo Go (Android) or Camera (iOS)
```

## Files
- `App.js` — both screens + navigation state (no router needed, keeps bundle tiny)
- `src/api.js` — `diagnoseLeaf()`, `fetchAdvisory()`, `playableAudio()`, `syncQueue()`
- `src/offlineQueue.js` — AsyncStorage queue: `enqueue()`, `pending()`, `markSynced()`, `history()`
- `src/language.js` — Pidgin/Hausa/Yoruba labels + recipe icons
