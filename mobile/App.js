// AgriPulse Edge — ultra-simple farmer mobile client (Expo).
// Screen 1: Camera/Home (giant Snap button + offline pill).
// Screen 2: Instant Diagnosis & Audio (big icon + dialect voice + 3 recipe cards).
import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Alert, Image, Modal, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { Audio } from 'expo-av';
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as Network from 'expo-network';
import { diagnoseLeaf, fetchAdvisory, fetchVoiceAudio, getBackendUrl, setBackendUrl, syncQueue } from './src/api';
import { LANGUAGES, RECIPE_ICONS, STRINGS, simpleName } from './src/language';
import * as queue from './src/offlineQueue';

const GREEN = '#0b4d2e';
const LIME = '#22c55e';

export default function App() {
  const [screen, setScreen] = useState('home');
  const [lang, setLang] = useState('pidgin');
  const [photo, setPhoto] = useState(null);
  const [result, setResult] = useState(null);
  const [advisory, setAdvisory] = useState(null);
  const [busy, setBusy] = useState(false);
  const [online, setOnline] = useState(false);
  const [pendingN, setPendingN] = useState(0);
  const [sound, setSound] = useState(null);
  const [permission, requestPermission] = useCameraPermissions();
  const [ipModal, setIpModal] = useState(false);
  const [ipDraft, setIpDraft] = useState('');
  const [backendLabel, setBackendLabel] = useState(getBackendUrl());
  const camRef = useRef(null);
  const t = STRINGS[lang];

  useEffect(() => {
    (async () => {
      setPendingN(await queue.pendingCount());
      try {
        const st = await Network.getNetworkStateAsync();
        const up = !!(st.isConnected && st.isInternetReachable !== false);
        setOnline(up);
        if (up) {
          const r = await syncQueue(queue, queue.markSynced);
          setPendingN(r.remaining);
        }
      } catch { /* fully offline: stay quiet */ }
    })();
    return () => { if (sound) sound.unloadAsync(); };
  }, []);


  async function onSnap() {
    if (!permission?.granted) {
      const r = await requestPermission();
      if (!r.granted) { Alert.alert('Camera needed', 'Allow camera so we fit see the sick leaf.'); return; }
    }
    try {
      setBusy(true);
      const pic = await camRef.current?.takePictureAsync({ quality: 0.7 });
      if (!pic?.uri) throw new Error('No photo captured');
      setPhoto(pic.uri);
      const diag = await diagnoseLeaf(pic.uri, lang);
      setResult(diag);
      const ctx = { crop_name: diag.crop_name, disease_detected: diag.disease_detected,
                    damage_percentage: diag.damage_percentage, severity: diag.severity };
      const adv = await fetchAdvisory(`My ${diag.crop_name} leaf get problem, wetin I fit do?`, lang, ctx);
      setAdvisory(adv);
      setScreen('result');
    } catch (e) {
      const entry = await queue.enqueue({ crop_name: 'unknown', disease_detected: 'pending sync',
        damage_percentage: 0, severity: 'low', language: lang, timestamp: new Date().toISOString() });
      setPendingN(await queue.pendingCount());
      Alert.alert('Saved offline', `No network — scan ${entry.client_scan_id} go sync later. (${e.message})`);
    } finally {
      setBusy(false);
    }
  }

  async function onPlay() {
    try {
      if (sound) { await sound.unloadAsync(); setSound(null); }
      const url = await fetchVoiceAudio(advisory?.spoken_reply || 'How body my friend!', lang);
      const { sound: s } = await Audio.Sound.createAsync({ uri: url });
      setSound(s);
      await s.playAsync();
    } catch (e) {
      Alert.alert('Audio wahala', e.message);
    }
  }

  async function onSave() {
    const rec = { crop_name: result?.crop_name, disease_detected: result?.disease_detected,
      damage_percentage: result?.damage_percentage, severity: result?.severity,
      language: lang, timestamp: new Date().toISOString(), photo };
    await queue.saveHistory(rec);
    try {
      if (online) {
        const r = await syncQueue(queue, queue.markSynced);
        setPendingN(r.remaining);
        Alert.alert('Saved & synced ✅', 'E don enter cooperative record.');
      } else {
        await queue.enqueue(rec);
        setPendingN(await queue.pendingCount());
        Alert.alert('Saved offline 💾', 'We go sync am when network show.');
      }
    } catch {
      await queue.enqueue(rec);
      setPendingN(await queue.pendingCount());
    }
    setScreen('home');
  }

  return (
    <SafeAreaView style={s.safe}>
      <View style={[s.pill, online ? s.pillOnline : s.pillOffline]}>
        <Text style={s.pillText}>{online ? '🌐 Online — syncing' : '⚡ 100% Offline Mode (0KB Data Used)'}</Text>
      </View>
      {!!pendingN && <Text style={s.queue}>{pendingN} scan(s) dey wait for network…</Text>}
      {screen === 'home' ? (
        <View style={s.home}>
          <Text style={s.title}>AgriPulse Edge 🌿</Text>
          <View style={s.langRow}>
            {LANGUAGES.map((l) => (
              <TouchableOpacity key={l.code} onPress={() => setLang(l.code)}
                style={[s.langPill, lang === l.code && s.langActive]}>
                <Text style={[s.langText, lang === l.code && s.langTextActive]}>{l.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
          <View style={s.camBox}>
            <CameraView ref={camRef} style={s.cam} facing="back" />
          </View>
          <TouchableOpacity style={s.snap} onPress={onSnap} disabled={busy}>
            {busy ? <ActivityIndicator color="#fff" size="large" /> : <Text style={s.snapText}>{t.snap}</Text>}
          </TouchableOpacity>
          {/* Tap backend label to switch LAN IP without editing source code */}
          <TouchableOpacity onPress={() => { setIpDraft(getBackendUrl()); setIpModal(true); }}>
            <Text style={s.backend}>🔧 Backend: {backendLabel} (tap to change)</Text>
          </TouchableOpacity>
          <Modal visible={ipModal} transparent animationType="slide" onRequestClose={() => setIpModal(false)}>
            <View style={s.modalWrap}>
              <View style={s.modalBox}>
                <Text style={s.modalTitle}>Laptop LAN address</Text>
                <Text style={s.modalHint}>Same Wi-Fi, e.g. http://192.168.1.50:8000</Text>
                <TextInput style={s.modalInput} value={ipDraft} onChangeText={setIpDraft}
                  placeholder="http://192.168.1.50:8000" autoCapitalize="none" autoCorrect={false} />
                <View style={s.modalRow}>
                  <TouchableOpacity style={s.modalCancel} onPress={() => setIpModal(false)}>
                    <Text style={s.modalCancelText}>Cancel</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={s.modalSave} onPress={() => {
                    const v = (ipDraft || '').trim() || 'http://192.168.0.115:8000';
                    setBackendUrl(v);
                    setBackendLabel(getBackendUrl());
                    setIpModal(false);
                  }}>
                    <Text style={s.modalSaveText}>Save</Text>
                  </TouchableOpacity>
                </View>
              </View>
            </View>
          </Modal>
        </View>
      ) : (
        <ScrollView contentContainerStyle={s.result}>
          {photo && <Image source={{ uri: photo }} style={s.thumb} />}
          {(() => { const sn = simpleName(result?.crop_name, result?.disease_detected); return (
            <View style={s.dxBox}>
              <Text style={s.dxIcon}>{sn.icon}</Text>
              <Text style={s.dxTitle}>{sn.title}</Text>
              <Text style={s.dxSub}>{result?.crop_name} • damage {result?.damage_percentage}% • {result?.severity}</Text>
            </View> ); })()}
          <TouchableOpacity style={s.play} onPress={onPlay}>
            <Text style={s.playText}>{t.play}</Text>
          </TouchableOpacity>
          {!!advisory?.spoken_reply && <Text style={s.reply}>“{advisory.spoken_reply}”</Text>}
          <Text style={s.how}>{t.howTo}</Text>
          {(result?.organic_remedies || []).slice(0, 3).map((r, i) => (
            <View key={i} style={s.card}>
              <Text style={s.cardTitle}>{RECIPE_ICONS[i % 3]} {i + 1}. {r.title}</Text>
              <Text style={s.cardBody}>{r.preparation}</Text>
            </View>
          ))}
          <TouchableOpacity style={s.save} onPress={onSave}>
            <Text style={s.saveText}>{t.save}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => setScreen('home')}><Text style={s.back}>← Snap another leaf</Text></TouchableOpacity>
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#f4faf4' },
  pill: { margin: 12, padding: 12, borderRadius: 999, alignItems: 'center' },
  pillOffline: { backgroundColor: GREEN },
  pillOnline: { backgroundColor: '#1565c0' },
  pillText: { color: '#fff', fontWeight: '800', fontSize: 15 },
  queue: { textAlign: 'center', color: '#854d0e', fontWeight: '700' },
  home: { flex: 1, padding: 16 },
  title: { fontSize: 30, fontWeight: '900', color: GREEN, textAlign: 'center' },
  langRow: { flexDirection: 'row', justifyContent: 'center', marginVertical: 10, flexWrap: 'wrap' },
  langPill: { borderWidth: 2, borderColor: GREEN, borderRadius: 999, paddingVertical: 8, paddingHorizontal: 12, margin: 4 },
  langActive: { backgroundColor: GREEN },
  langText: { color: GREEN, fontWeight: '800', fontSize: 14 },
  langTextActive: { color: '#fff' },
  camBox: { height: 320, borderRadius: 20, overflow: 'hidden', backgroundColor: '#000' },
  cam: { flex: 1 },
  snap: { backgroundColor: LIME, borderRadius: 24, padding: 26, marginTop: 16, alignItems: 'center', elevation: 4 },
  snapText: { color: '#052e16', fontSize: 26, fontWeight: '900' },
  backend: { textAlign: 'center', color: '#888', marginTop: 8, fontSize: 12 },
  modalWrap: { flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'center', padding: 24 },
  result: { padding: 16, paddingBottom: 40 },
  thumb: { width: '100%', height: 200, borderRadius: 16 },
  dxBox: { backgroundColor: GREEN, borderRadius: 20, padding: 20, marginTop: 12, alignItems: 'center' },
  dxIcon: { fontSize: 56 },
  dxTitle: { color: '#fff', fontSize: 26, fontWeight: '900', textAlign: 'center' },
  dxSub: { color: '#bbf7d0', fontWeight: '700', marginTop: 4 },
  play: { backgroundColor: '#facc15', borderRadius: 20, padding: 22, marginTop: 12, alignItems: 'center' },
  playText: { fontSize: 20, fontWeight: '900', color: '#422006' },
  reply: { fontStyle: 'italic', fontSize: 17, color: '#123f27', marginTop: 10 },
  how: { fontSize: 20, fontWeight: '900', color: GREEN, marginTop: 14 },
  card: { backgroundColor: '#fff', borderLeftWidth: 6, borderLeftColor: LIME, borderRadius: 12, padding: 14, marginTop: 10 },
  cardTitle: { fontSize: 18, fontWeight: '900', color: GREEN },
  cardBody: { fontSize: 15, color: '#333', marginTop: 4 },
  save: { backgroundColor: GREEN, borderRadius: 20, padding: 20, marginTop: 14, alignItems: 'center' },
  saveText: { color: '#fff', fontSize: 20, fontWeight: '900' },
  back: { textAlign: 'center', color: GREEN, fontWeight: '800', marginTop: 12, fontSize: 16 },
  modalBox: { backgroundColor: '#fff', borderRadius: 18, padding: 18 },
  modalTitle: { fontSize: 20, fontWeight: '900', color: GREEN },
  modalHint: { color: '#666', marginVertical: 6 },
  modalInput: { borderWidth: 2, borderColor: GREEN, borderRadius: 12, padding: 12, fontSize: 16 },
  modalRow: { flexDirection: 'row', justifyContent: 'flex-end', marginTop: 12 },
  modalCancel: { padding: 12, marginRight: 8 },
  modalCancelText: { color: '#666', fontWeight: '800', fontSize: 16 },
  modalSave: { backgroundColor: GREEN, borderRadius: 12, paddingVertical: 12, paddingHorizontal: 22 },
  modalSaveText: { color: '#fff', fontWeight: '900', fontSize: 16 },
});

