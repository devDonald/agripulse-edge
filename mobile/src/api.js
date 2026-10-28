// Backend API client + auto-sync of the offline queue.
// Works with: POST /api/v1/diagnose-edge, /api/v1/voice-advisory,
//             /api/v1/voice-synthesize, /api/v1/mobile/sync-batch
//
// Dynamic URL: call setBackendUrl('http://192.168.1.50:8000') from the app's
// IP switcher — no source-code edits needed in the field.
// Production is the safe default. The in-app override remains useful for
// local field testing, but no release build silently points at localhost.
let currentBackendUrl = 'https://agripulse.zentreeca.org';

export const getBackendUrl = () => currentBackendUrl;
export const setBackendUrl = (url) => {
  const candidate = String(url || '').trim().replace(/\/$/, '');
  if (!/^https?:\/\/[^\s]+$/i.test(candidate)) throw new Error('Enter a valid HTTPS or LAN HTTP URL');
  currentBackendUrl = candidate;
};
// Back-compat alias for older imports.
export const BACKEND_URL = currentBackendUrl;

async function request(url, options = {}, timeoutMs = 45000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { ...options, signal: controller.signal });
    return res;
  } catch (error) {
    if (error?.name === 'AbortError') throw new Error('Request timed out. Check your connection and try again.');
    throw new Error('Unable to reach AgriPulse. Check your connection.');
  } finally { clearTimeout(timer); }
}

export async function diagnoseLeaf(photoUri, language = 'pidgin') {
  const form = new FormData();
  form.append('file', { uri: photoUri, name: 'leaf.jpg', type: 'image/jpeg' });
  const res = await request(`${getBackendUrl()}/api/v1/diagnose-edge`, { method: 'POST', body: form });
  if (!res.ok) throw new Error(`diagnose failed (${res.status})`);
  return res.json();
}

export async function fetchAdvisory(query, language, diagnosisContext) {
  const res = await request(`${getBackendUrl()}/api/v1/voice-advisory`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, language, diagnosis_context: diagnosisContext || null }),
  });
  if (!res.ok) throw new Error(`advisory failed (${res.status})`);
  return res.json();
}

export async function fetchVoiceAudio(text, language) {
  const res = await request(`${getBackendUrl()}/api/v1/voice-synthesize`, {
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
  const res = await request(`${getBackendUrl()}/api/v1/mobile/sync-batch`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`sync failed (${res.status})`);
  const data = await res.json();
  await markSynced((data.scans || []).map((s) => s.client_scan_id));
  return { synced: data.accepted || 0, remaining: await queue.pendingCount() };
}
