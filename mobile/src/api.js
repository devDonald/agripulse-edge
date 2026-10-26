// Backend API client + auto-sync of the offline queue.
// Works with: POST /api/v1/diagnose-edge, /api/v1/voice-advisory,
//             /api/v1/voice-synthesize, /api/v1/mobile/sync-batch
export const BACKEND_URL = 'http://YOUR_LAPTOP_IP:8000'; // <-- phone + laptop on same Wi-Fi

export async function diagnoseLeaf(photoUri, language = 'pidgin') {
  const form = new FormData();
  form.append('file', { uri: photoUri, name: 'leaf.jpg', type: 'image/jpeg' });
  const res = await fetch(`${BACKEND_URL}/api/v1/diagnose-edge`, { method: 'POST', body: form });
  if (!res.ok) throw new Error(`diagnose failed (${res.status})`);
  return res.json();
}

export async function fetchAdvisory(query, language, diagnosisContext) {
  const res = await fetch(`${BACKEND_URL}/api/v1/voice-advisory`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, language, diagnosis_context: diagnosisContext || null }),
  });
  if (!res.ok) throw new Error(`advisory failed (${res.status})`);
  return res.json();
}

export async function fetchVoiceAudio(text, language) {
  const res = await fetch(`${BACKEND_URL}/api/v1/voice-synthesize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, language }),
  });
  if (!res.ok) throw new Error(`audio failed (${res.status})`);
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

/** Push queued offline scans; returns { synced, remaining }. */
export async function syncQueue(queue, markSynced, farmerId = 'field-phone-1') {
  const items = await queue.pending();
  if (!items.length) return { synced: 0, remaining: 0 };
  const payload = {
    farmer_id: farmerId,
    scans: items.map((s) => ({
      client_scan_id: s.client_scan_id, crop_name: s.crop_name, disease_detected: s.disease_detected,
      damage_percentage: s.damage_percentage, severity: s.severity, language: s.language,
      latitude: s.latitude ?? null, longitude: s.longitude ?? null, timestamp: s.timestamp,
    })),
  };
  const res = await fetch(`${BACKEND_URL}/api/v1/mobile/sync-batch`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`sync failed (${res.status})`);
  const data = await res.json();
  await markSynced((data.scans || []).map((s) => s.client_scan_id));
  return { synced: data.accepted || 0, remaining: await queue.pendingCount() };
}
