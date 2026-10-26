// Offline queue: pending scans + saved history, persisted in AsyncStorage.
import AsyncStorage from '@react-native-async-storage/async-storage';

const QUEUE_KEY = 'agripulse_pending_scans_v1';
const HISTORY_KEY = 'agripulse_history_v1';

async function read(key) {
  try {
    const raw = await AsyncStorage.getItem(key);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

async function write(key, value) {
  await AsyncStorage.setItem(key, JSON.stringify(value));
}

export async function enqueue(scan) {
  const q = await read(QUEUE_KEY);
  const entry = { ...scan, client_scan_id: scan.client_scan_id || `local-${Date.now()}`, queued_at: new Date().toISOString() };
  q.push(entry);
  await write(QUEUE_KEY, q);
  return entry;
}

export async function pending() {
  return read(QUEUE_KEY);
}

export async function pendingCount() {
  return (await read(QUEUE_KEY)).length;
}

export async function markSynced(clientIds) {
  const ids = new Set(clientIds || []);
  const q = await read(QUEUE_KEY);
  await write(QUEUE_KEY, q.filter((s) => !ids.has(s.client_scan_id)));
}

export async function saveHistory(record) {
  const h = await read(HISTORY_KEY);
  h.unshift(record);
  await write(HISTORY_KEY, h.slice(0, 50));
}

export async function history() {
  return read(HISTORY_KEY);
}
