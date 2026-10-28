# AgriPulse Edge — Expo field client

The Expo client gives extension workers a camera-first workflow with persistent offline capture.

## Current behavior

1. **Connected:** capture a leaf, call the diagnostic API, receive diagnosis and remedies, then request spoken advice.
2. **Disconnected:** retain the local photo and queue entry in AsyncStorage.
3. **Reconnected:** diagnose each queued photo, sync the real result to `/api/v1/mobile/sync-batch`, and remove acknowledged entries.

This is reconnect-safe offline capture, not yet true on-device inference. True zero-data diagnosis requires packaging and invoking an ExecuTorch `.pte` model through a native module or Expo development build.

## Configure and run

Tap the backend address in the app to set the deployed HTTPS API or a laptop LAN URL.

```bash
cd mobile
npm install
npx expo start
```

For a competition demo, prefer a stable deployed HTTPS API. A hard-coded private LAN address is only suitable for local development.
