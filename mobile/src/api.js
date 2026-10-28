// Backend API client + auto-sync of the offline queue.
// Works with: POST /api/v1/diagnose-edge, /api/v1/voice-advisory,
//             /api/v1/voice-synthesize, /api/v1/mobile/sync-batch
//
// Dynamic URL: call setBackendUrl('http://192.168.1.50:8000') from the app's
// IP switcher — no source-code edits needed in the field.
let currentBackendUrl = 'http://192.168.0.115:8000'; // autodetected host LAN IP

export const getBackendUrl = () => currentBackendUrl;
export const setBackendUrl = (url) => {
  currentBackendUrl = String(url || '').replace(/\/$/, '');
};
// Back-compat alias for older imports.
export const BACKEND_URL = currentBackendUrl;

export async function diagnoseLeaf(photoUri, language = 'pidgin') {
  const form = new FormData();
  form.append('file', { uri: photoUri, name: 'leaf.jpg', type: 'image/jpeg' });
  const res = await fetch(`${getBackendUrl()}/api/v1/diagnose-edge`, { method: 'POST', body: form });
  if (!res.ok) throw new Error(`diagnose failed (${res.status})`);
  return res.json();
}

export async function fetchAdvisory(query, language, diagnosisContext) {
  const res = await fetch(`${getBackendUrl()}/api/v1/voice-advisory`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, language, diagnosis_context: diagnosisContext || null }),
  });
  if (!res.ok) throw new Error(`advisory failed (${res.status})`);
  return res.json();
}

export async function fetchVoiceAudio(text, language) {
  const res = await fetch(`${getBackendUrl()}/api/v1/voice-synthesize`, {
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
  const prepared = [];
  for (const item of items) {
    let scan = item;
    // Keep disconnected captures useful: once connectivity returns, diagnose
    // the saved image before syncing instead of storing an unknown placeholder.
    if (item.photo && item.disease_detected === 'pending diagnosis') {
      const diag = await diagnoseLeaf(item.photo, item.language);
      scan = { ...item, crop_name: diag.crop_name, disease_detected: diag.disease_detected,
        damage_percentage: diag.damage_percentage, severity: diag.severity };
    }
    prepared.push(scan);
  }
  const payload = {
    farmer_id: farmerId,
    scans: prepared.map((s) => ({
      client_scan_id: s.client_scan_id, crop_name: s.crop_name, disease_detected: s.disease_detected,
      damage_percentage: s.damage_percentage, severity: s.severity, language: s.language,
      latitude: s.latitude ?? null, longitude: s.longitude ?? null, timestamp: s.timestamp,
    })),
  };
  const res = await fetch(`${getBackendUrl()}/api/v1/mobile/sync-batch`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`sync failed (${res.status})`);
  const data = await res.json();
  await markSynced((data.scans || []).map((s) => s.client_scan_id));
  return { synced: data.accepted || 0, remaining: await queue.pendingCount() };
}
