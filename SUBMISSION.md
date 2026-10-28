# AgriPulse Edge — Hackathon Submission

## One-line pitch

AgriPulse turns one crop photo into a measured diagnosis and spoken field action, delivered through web, mobile, or WhatsApp in Pidgin, Hausa, Yoruba, and simple English.

## Track and theme

- **Recommended track:** Startup if the team intends to continue as a product; Indie only if submitting as an individual.
- **Theme:** Build for Your World.
- **Why it fits:** It applies Meta’s newest image, reasoning, segmentation, and messaging capabilities to crop protection in low-connectivity communities.

## What works in the submitted build

1. A farmer or extension officer submits one leaf photo through web, Expo mobile, or WhatsApp.
2. A local visual gate rejects non-leaf photos and provides a crop-shape guard before paid inference.
3. Muse Image is attempted for pixel-grounded diagnosis when Meta Model API credentials are configured. Muse reasoning refines pathology while the crop guard prevents cross-crop hallucinations.
4. SAM 3.1 is attempted for lesion segmentation; a deterministic spatial-mask fallback keeps the demo functional if the remote model is unavailable.
5. One severity policy converts measured damage into low, moderate, or severe across every channel.
6. The response includes three practical actions and spoken guidance in four languages.
7. Web, mobile, and WhatsApp cases enter one idempotent cooperative record stream.

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

## Reliability evidence

- Upload validation and non-leaf rejection before paid model calls.
- Cloud retry and deterministic fallback behavior.
- Confidence gate for uncertain diagnoses.
- Canonical damage-to-severity policy.
- Idempotent mobile sync and WhatsApp retry suppression.
- WhatsApp signature verification when `WHATSAPP_APP_SECRET` is set.
- Correlation IDs, rate limits, readiness checks, and persistent field records.
- Automated robustness and cross-channel contract tests.

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
