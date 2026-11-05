const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
let diagnosis = null;
let advisory = null;
let currentFile = null;
let isAdminMode = false;

const CROP_LABELS = {
  cassava: 'Cassava',
  maize: 'Maize (Corn)',
  tomato: 'Tomato',
  yam: 'Yam',
  cowpea: 'Cowpea (Beans)',
  sorghum: 'Sorghum (Guinea corn)',
  rice: 'Rice',
  pepper: 'Pepper',
  okra: 'Okra',
  groundnut: 'Groundnut (Peanut)',
  sweet_potato: 'Sweet potato',
};

function formatDiseaseName(raw) {
  if (!raw) return 'Condition identified';
  // Strip parenthetical Latin names and acronyms like (Puccinia sorghi), (CMD)
  return raw.replace(/\s*\([^)]*\)/g, '').trim();
}

function formatConfidence(conf) {
  if (conf >= 0.8) return 'High confidence';
  if (conf >= 0.6) return 'Moderate confidence';
  return 'Review advised';
}

function toast(message, error = false) {
  const el = $('#toast');
  if (!el) return;
  el.textContent = message;
  el.className = `toast show${error ? ' error' : ''}`;
  setTimeout(() => el.classList.remove('show'), 3600);
}

function setAdminMode(enable, syncUrl = false) {
  isAdminMode = enable;
  document.body.classList.toggle('admin-mode', isAdminMode);
  localStorage.setItem('agripulse_role', isAdminMode ? 'admin' : 'public');

  const label = $('#workspace-label');
  if (label) label.textContent = isAdminMode ? 'ADMIN & OPERATIONS' : 'FARMER CLINIC';

  const kicker = $('#view-kicker');
  if (kicker) kicker.textContent = isAdminMode ? 'AGRICULTURAL OPERATIONS / ADMIN' : 'FARMER EXTENSION CLINIC';

  const pill = $('#role-pill');
  if (pill) {
    pill.textContent = isAdminMode ? 'Admin Mode' : 'Farmer View';
    pill.className = `role-pill ${isAdminMode ? 'admin' : 'farmer'}`;
  }

  const toggleBtn = $('#role-toggle-btn');
  if (toggleBtn) {
    toggleBtn.innerHTML = isAdminMode
      ? '<span class="role-icon">←</span><span class="role-text">Switch to Farmer view</span>'
      : '<span class="role-icon">🔐</span><span class="role-text">Staff / Admin portal</span>';
  }

  const topToggle = $('#top-admin-toggle');
  if (topToggle) {
    topToggle.textContent = isAdminMode ? 'Farmer View' : 'Admin Portal';
  }

  // If switched to public mode while on an admin-only view, redirect to clinic
  const currentView = $('.side-link.active')?.dataset.view;
  if (!isAdminMode && ['command', 'history', 'models', 'whatsapp'].includes(currentView)) {
    showView('clinic');
  }

  // Re-render diagnosis if one is loaded
  if (diagnosis) {
    renderDiagnosis();
  }

  if (syncUrl) {
    const url = new URL(location.href);
    if (isAdminMode) {
      url.searchParams.set('mode', 'admin');
    } else {
      url.searchParams.delete('mode');
      url.searchParams.delete('role');
    }
    window.history.replaceState({}, '', url.toString());
  }
}

function showView(name) {
  // If attempting to open admin view without admin mode, enable admin mode automatically
  if (['command', 'history', 'models', 'whatsapp'].includes(name) && !isAdminMode) {
    setAdminMode(true, true);
  }

  $$('.app-view').forEach((v) => v.classList.toggle('active', v.id === name));
  $$('.side-link').forEach((b) => b.classList.toggle('active', b.dataset.view === name));
  
  const titles = {
    clinic: 'Crop clinic',
    command: 'Command center',
    history: 'Field records',
    whatsapp: 'WhatsApp Business Cloud API',
    models: 'System & model diagnostics',
  };
  $('#view-title').textContent = titles[name] || 'Crop clinic';
  document.body.classList.remove('nav-open');

  if (name === 'history') loadHistoryRecords();
  if (name === 'models') loadModelCatalog();
}

$$('.side-link').forEach((b) => b.addEventListener('click', () => showView(b.dataset.view)));
$('.mobile-nav')?.addEventListener('click', () => document.body.classList.toggle('nav-open'));

$('#role-toggle-btn')?.addEventListener('click', () => {
  setAdminMode(!isAdminMode, true);
  toast(isAdminMode ? 'Switched to Admin & Operations Mode' : 'Switched to Public Farmer View');
});

$('#top-admin-toggle')?.addEventListener('click', () => {
  setAdminMode(!isAdminMode, true);
  toast(isAdminMode ? 'Switched to Admin & Operations Mode' : 'Switched to Public Farmer View');
});

// Initialize role mode from URL or localStorage
const urlParams = new URLSearchParams(location.search);
const requestedMode = urlParams.get('mode') || urlParams.get('role');
const savedRole = localStorage.getItem('agripulse_role');

if (['admin', 'command', 'history', 'models', 'staff', 'whatsapp'].includes(requestedMode)) {
  setAdminMode(true);
  if (['command', 'history', 'models', 'whatsapp'].includes(requestedMode)) {
    showView(requestedMode);
  }
} else if (savedRole === 'admin' && !requestedMode) {
  setAdminMode(true);
} else {
  setAdminMode(false);
}

const fileInput = $('#leaf-file');
fileInput?.addEventListener('change', () => {
  const file = fileInput.files[0];
  if (!file) return;
  if (file.size > 10 * 1024 * 1024) {
    toast('Please choose an image smaller than 10MB.', true);
    fileInput.value = '';
    return;
  }
  currentFile = file;
  $$('.preset-chip').forEach((c) => c.classList.remove('active'));
  const url = URL.createObjectURL(file);
  $('#preview').src = url;
  $('#drop-zone').classList.add('has-image');
  $('#diagnose').disabled = false;
});

// Quick Field Presets handling (11 crops + healthy leaf)
$$('.preset-chip').forEach((chip) => {
  chip.addEventListener('click', async () => {
    $$('.preset-chip').forEach((c) => c.classList.remove('active'));
    chip.classList.add('active');
    const sampleName = chip.dataset.sample;
    const cropHint = chip.dataset.crop || '';
    if (cropHint && $('#crop-hint')) {
      $('#crop-hint').value = cropHint;
    }
    toast(`Loading ${chip.textContent.trim()} sample…`);
    try {
      const res = await fetch(`/sample_data/${sampleName}`);
      if (!res.ok) throw new Error(`Could not load ${sampleName}`);
      const blob = await res.blob();
      currentFile = new File([blob], sampleName, { type: blob.type || 'image/jpeg' });
      const url = URL.createObjectURL(blob);
      $('#preview').src = url;
      $('#drop-zone').classList.add('has-image');
      $('#diagnose').disabled = false;
    } catch (err) {
      toast(`Failed to load preset: ${err.message}`, true);
    }
  });
});

$('#diagnose')?.addEventListener('click', async () => {
  if (!currentFile) {
    toast('Please select or upload a leaf photo first.', true);
    return;
  }
  const button = $('#diagnose');
  button.disabled = true;
  button.classList.add('loading');
  button.querySelector('span').textContent = 'Analysing symptoms…';

  const form = new FormData();
  form.append('file', currentFile);
  
  // Use admin engine override only if in admin mode, otherwise default to standard cloud/auto
  const edge = isAdminMode && $('#analysis-mode')?.value === 'edge';
  let endpoint = edge ? '/api/v1/diagnose-edge' : '/api/v1/diagnose';
  const cropHint = $('#crop-hint')?.value;
  if (cropHint) {
    endpoint += `?expected_crop=${encodeURIComponent(cropHint)}`;
  }

  try {
    const response = await fetch(endpoint, { method: 'POST', body: form });
    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.detail || 'Diagnosis failed');
    }
    diagnosis = await response.json();

    // Sync into field records (idempotent SQLite)
    await fetch('/api/v1/mobile/sync', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        farmer_id: isAdminMode ? 'admin-console' : 'web-farmer',
        client_scan_id: `web-${Date.now()}`,
        crop_name: diagnosis.crop_name,
        disease_detected: diagnosis.disease_detected,
        damage_percentage: diagnosis.damage_percentage,
        severity: diagnosis.severity,
        language: $('#language')?.value || 'pidgin',
        timestamp: new Date().toISOString(),
      }),
    }).catch(() => null);

    const ctx = {
      crop_name: diagnosis.crop_name,
      disease_detected: diagnosis.disease_detected,
      damage_percentage: diagnosis.damage_percentage,
      severity: diagnosis.severity,
    };
    const advRes = await fetch('/api/v1/voice-advisory', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: `What should I do about ${diagnosis.disease_detected} on my ${diagnosis.crop_name}?`,
        language: $('#language')?.value || 'pidgin',
        diagnosis_context: ctx,
      }),
    });
    if (advRes.ok) advisory = await advRes.json();
    renderDiagnosis();
    toast('Diagnosis complete. Treatment guidance is ready.');
  } catch (err) {
    toast(err.message || 'Could not complete the diagnosis.', true);
  } finally {
    button.disabled = false;
    button.classList.remove('loading');
    button.querySelector('span').textContent = 'Analyse crop leaf';
  }
});

function renderDiagnosis() {
  if (!diagnosis) return;
  resetAdviceAudio();

  const cleanName = formatDiseaseName(diagnosis.disease_detected);
  $('#result-disease').textContent = cleanName;

  const rawCrop = (diagnosis.crop_name || 'crop').toLowerCase();
  const cropDisplayName = CROP_LABELS[rawCrop] || (diagnosis.crop_name || 'Crop');
  const conf = diagnosis.confidence || 0;

  if (isAdminMode) {
    const engine =
      diagnosis.segmentation?.method_used ||
      diagnosis.model_used ||
      (diagnosis.edge_metrics ? 'ExecuTorch Edge' : 'Meta Muse Spark');
    $('#result-crop').textContent = `[ADMIN] ${cropDisplayName.toUpperCase()} · ${Math.round(conf * 100)}% confidence · Engine: ${engine}`;
    if ($('#result-tag')) {
      $('#result-tag').textContent = diagnosis.segmentation?.method_used || 'SAM 2 Lesion Mask';
    }
  } else {
    $('#result-crop').textContent = `${cropDisplayName} · Symptoms identified · ${formatConfidence(conf)}`;
    if ($('#result-tag')) {
      $('#result-tag').textContent = 'Leaf damage analysis';
    }
  }

  $('#result-damage').textContent = `${Math.round(diagnosis.damage_percentage || 0)}%`;
  $('#result-severity').textContent = (diagnosis.severity || 'mild').toUpperCase();

  // Crop hint notice
  const hintEl = $('#result-hint-note');
  if (hintEl) {
    if (diagnosis.hint_note) {
      hintEl.textContent = `ℹ️ ${diagnosis.hint_note}`;
      hintEl.hidden = false;
    } else {
      hintEl.hidden = true;
    }
  }

  // Symptoms list
  const symEl = $('#result-symptoms');
  if (symEl) {
    const symptoms = diagnosis.symptoms || [];
    symEl.innerHTML = symptoms.length
      ? symptoms.map((s) => `<span class="symptom-tag">• ${s}</span>`).join('')
      : '<span class="symptom-tag">• Typical foliar symptoms observed</span>';
  }

  // Leaf image / damage outline
  if (diagnosis.segmentation?.mask_overlay_base64) {
    $('#result-image').src = `data:image/png;base64,${diagnosis.segmentation.mask_overlay_base64}`;
  } else if ($('#preview')?.src) {
    $('#result-image').src = $('#preview').src;
  }

  const remedies = diagnosis.organic_remedies || [];
  $('#remedies').innerHTML =
    remedies
      .slice(0, 3)
      .map(
        (r, i) =>
          `<div class="remedy"><i>${i + 1}</i><div><b>${r.title || 'Treatment step'}</b><p>${r.preparation || r.description || ''}</p></div></div>`
      )
      .join('') || '<p>Review the voice guidance for next steps.</p>';

  $('#result-panel').hidden = false;
  $('#result-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

let currentAudioUrl = null;
let currentAudioLang = null;

function resetAdviceAudio() {
  const audio = $('#advice-audio');
  if (audio) {
    audio.pause();
    audio.currentTime = 0;
  }
  if (currentAudioUrl) {
    try {
      URL.revokeObjectURL(currentAudioUrl);
    } catch (_) {}
    currentAudioUrl = null;
    currentAudioLang = null;
  }
  const btn = $('#play-advice');
  if (btn) {
    btn.innerHTML = '▶ <span>Play voice guidance</span>';
    btn.classList.remove('playing');
    btn.disabled = false;
  }
}

const adviceAudio = $('#advice-audio');
if (adviceAudio) {
  adviceAudio.addEventListener('play', () => {
    const btn = $('#play-advice');
    if (btn) {
      btn.innerHTML = '⏸ <span>Pause voice guidance</span>';
      btn.classList.add('playing');
    }
  });

  adviceAudio.addEventListener('pause', () => {
    const btn = $('#play-advice');
    if (btn) {
      if (adviceAudio.ended) {
        btn.innerHTML = '▶ <span>Play voice guidance</span>';
      } else {
        btn.innerHTML = '▶ <span>Resume voice guidance</span>';
      }
      btn.classList.remove('playing');
    }
  });

  adviceAudio.addEventListener('ended', () => {
    const btn = $('#play-advice');
    if (btn) {
      btn.innerHTML = '▶ <span>Play voice guidance</span>';
      btn.classList.remove('playing');
    }
  });

  adviceAudio.addEventListener('error', () => {
    const btn = $('#play-advice');
    if (btn) {
      btn.innerHTML = '▶ <span>Play voice guidance</span>';
      btn.classList.remove('playing');
    }
    toast('Audio playback failed.', true);
  });
}

$('#play-advice')?.addEventListener('click', async () => {
  if (!advisory?.spoken_reply) {
    return toast('Voice guidance is not available for this result.', true);
  }
  const audio = $('#advice-audio');
  const btn = $('#play-advice');
  const lang = $('#language')?.value || 'pidgin';

  // Toggle: If currently playing, clicking pauses playback
  if (!audio.paused && !audio.ended) {
    audio.pause();
    return;
  }

  // Toggle: If already loaded and paused for the same language, resume
  if (currentAudioUrl && currentAudioLang === lang && audio.src) {
    try {
      await audio.play();
    } catch (err) {
      toast(err.message || 'Audio playback error', true);
    }
    return;
  }

  // Otherwise, synthesize new audio for current advisory & language
  try {
    btn.disabled = true;
    btn.innerHTML = '⏳ <span>Generating voice…</span>';
    const res = await fetch('/api/v1/voice-synthesize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: advisory.spoken_reply.slice(0, 500), language: lang }),
    });
    if (!res.ok) throw new Error('Audio generation failed');
    if (currentAudioUrl) {
      try {
        URL.revokeObjectURL(currentAudioUrl);
      } catch (_) {}
    }
    currentAudioUrl = URL.createObjectURL(await res.blob());
    currentAudioLang = lang;
    audio.src = currentAudioUrl;
    await audio.play();
  } catch (err) {
    toast(err.message || 'Could not play voice guidance.', true);
    btn.innerHTML = '▶ <span>Play voice guidance</span>';
    btn.classList.remove('playing');
  } finally {
    btn.disabled = false;
  }
});

$('#language')?.addEventListener('change', () => {
  resetAdviceAudio();
});

async function loadHistoryRecords() {
  try {
    const r = await fetch('/api/v1/mobile/history?farmer_id=coop:all&limit=25');
    const d = await r.json();
    const rows = d.scans || d.history || (Array.isArray(d) ? d : []);
    $('#history-list').innerHTML = rows.length
      ? rows
          .map(
            (x) =>
              `<div class="data-row"><b>${(x.crop_name || 'Crop').toUpperCase()} — ${formatDiseaseName(x.disease_detected)}</b><span>${Math.round(x.damage_percentage || 0)}% damage · Severity: ${x.severity || 'low'} · Origin: ${x.farmer_id || 'mobile'} · ${x.timestamp ? new Date(x.timestamp).toLocaleString() : 'Recent'}</span></div>`
          )
          .join('')
      : '<p class="muted">No synced records yet. Scans from mobile and web will appear here.</p>';
  } catch (e) {
    toast('Could not load field records.', true);
  }
}

async function loadModelCatalog() {
  try {
    const r = await fetch('/api/v1/models');
    const d = await r.json();
    const readyRes = await fetch('/ready').then((res) => res.json()).catch(() => ({}));

    const cloudStatus = $('#admin-cloud-status');
    if (cloudStatus) {
      cloudStatus.textContent = readyRes.cloud_key_configured ? 'Active (Live Meta API)' : 'Active (Local Fallback)';
      cloudStatus.className = readyRes.cloud_key_configured ? 'status-active' : 'status-warn';
    }

    $('#model-list').innerHTML = `
      <div class="admin-data-header">CONFIGURED MODEL CATALOG (${(d.models || []).length} registered)</div>
      ${(d.models || [])
        .map(
          (x) =>
            `<div class="data-row"><b>${x.label || x.name || x.id}</b><span>${x.purpose || x.description || 'Active'} · Deployment: <strong>${x.tier || 'Edge/Cloud'}</strong></span></div>`
        )
        .join('')}
    `;
  } catch (e) {
    toast('Could not load the model catalog.', true);
  }
}

async function loadBenchmarks() {
  try {
    toast('Running on-device edge benchmark…');
    const r = await fetch('/api/v1/edge/benchmark');
    const data = await r.json();
    $('#benchmark-list').innerHTML = `
      <div class="admin-data-header">EXECUTORCH HARDWARE TELEMETRY</div>
      ${Object.entries(data)
        .map(
          ([k, v]) =>
            `<div class="data-row"><b>${k}</b><span>Latency: <strong>${v.latency_ms} ms</strong> · Memory: <strong>${v.ram_mb} MB</strong> · Format: <strong>${v.quantization}</strong></span></div>`
        )
        .join('')}
    `;
    toast('Edge benchmark complete.');
  } catch (e) {
    toast('Benchmark run failed.', true);
  }
}

$('#load-history')?.addEventListener('click', loadHistoryRecords);
$('#load-models')?.addEventListener('click', loadModelCatalog);
$('#load-benchmarks')?.addEventListener('click', loadBenchmarks);

// ─────────────────────────────────────────────────────────────────────────────
// Meta WhatsApp Business Cloud Channel Simulator
// ─────────────────────────────────────────────────────────────────────────────

$('#btn-open-wa')?.addEventListener('click', () => {
  setAdminMode(true, true);
  showView('whatsapp');
  toast('Opened WhatsApp Business Cloud Channel Sandbox');
});

async function simulateWhatsAppMessage({ type, text, sample, caption }) {
  const chatBox = $('#wa-chat-box');
  if (!chatBox) return;

  // 1. Append User bubble
  const userBubble = document.createElement('div');
  userBubble.className = 'msg-bubble user';
  const nowTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  let userContent = text || caption || 'Sent photo';
  if (type === 'image') {
    userContent = `📸 <i>[Sent leaf photo: ${sample || 'leaf'}]</i><br>${caption || ''}`;
  }
  userBubble.innerHTML = `
    <div class="msg-text">${userContent}</div>
    <span class="msg-time">${nowTime} ✓✓</span>
  `;
  chatBox.appendChild(userBubble);
  chatBox.scrollTop = chatBox.scrollHeight;

  // 2. Append Typing indicator
  const typingBubble = document.createElement('div');
  typingBubble.className = 'msg-bubble bot typing';
  typingBubble.innerHTML = `<div class="msg-text"><em>AgriPulse Farm Doctor is typing…</em></div>`;
  chatBox.appendChild(typingBubble);
  chatBox.scrollTop = chatBox.scrollHeight;

  // 3. Make simulation API call
  try {
    const payload = {
      message_type: type,
      text_body: text || caption,
      sample_preset: sample || null,
    };
    const res = await fetch('/api/v1/whatsapp/simulate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error('WhatsApp simulation request failed');
    const data = await res.json();

    // Remove typing bubble
    typingBubble.remove();

    // 4. Append Bot reply bubble
    const botBubble = document.createElement('div');
    botBubble.className = 'msg-bubble bot';
    const formattedReply = (data.reply || 'Message received.')
      .replace(/\n/g, '<br>')
      .replace(/\*([^*]+)\*/g, '<b>$1</b>');

    let audioPlayerHtml = '';
    if (data.spoken_reply) {
      audioPlayerHtml = `
        <div class="wa-audio-player">
          <button type="button" class="wa-play-btn" data-spoken="${encodeURIComponent(data.spoken_reply)}" data-lang="${data.language || 'pidgin'}">▶ Play Voice Note (MP3)</button>
        </div>
      `;
    }

    botBubble.innerHTML = `
      <div class="msg-author">AgriPulse Farm Doctor</div>
      <div class="msg-text">${formattedReply}</div>
      ${audioPlayerHtml}
      <span class="msg-time">${nowTime}</span>
    `;
    chatBox.appendChild(botBubble);
    chatBox.scrollTop = chatBox.scrollHeight;

    // Wire audio button inside the bubble
    const audioBtn = botBubble.querySelector('.wa-play-btn');
    if (audioBtn) {
      audioBtn.addEventListener('click', async () => {
        const spoken = decodeURIComponent(audioBtn.dataset.spoken);
        const lang = audioBtn.dataset.lang;
        audioBtn.disabled = true;
        audioBtn.textContent = '⏳ Loading audio…';
        try {
          const synthRes = await fetch('/api/v1/voice-synthesize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: spoken.slice(0, 500), language: lang }),
          });
          if (!synthRes.ok) throw new Error('Voice fetch failed');
          const blob = await synthRes.blob();
          const audioUrl = URL.createObjectURL(blob);
          const audio = new Audio(audioUrl);
          audioBtn.textContent = '⏸ Playing voice note…';
          audio.onended = () => {
            audioBtn.textContent = '▶ Play Voice Note (MP3)';
            audioBtn.disabled = false;
          };
          audio.onerror = () => {
            audioBtn.textContent = '▶ Play Voice Note (MP3)';
            audioBtn.disabled = false;
          };
          await audio.play();
        } catch (e) {
          audioBtn.textContent = '▶ Play Voice Note (MP3)';
          audioBtn.disabled = false;
          toast('Audio playback failed', true);
        }
      });
    }

    toast('WhatsApp event processed & synced to audit log');
  } catch (err) {
    typingBubble.remove();
    const errBubble = document.createElement('div');
    errBubble.className = 'msg-bubble bot error';
    errBubble.innerHTML = `<div class="msg-text">⚠️ <i>Error processing message: ${err.message}</i></div>`;
    chatBox.appendChild(errBubble);
    chatBox.scrollTop = chatBox.scrollHeight;
  }
}

$$('.sim-chip').forEach((chip) => {
  chip.addEventListener('click', () => {
    const type = chip.dataset.type;
    const text = chip.dataset.text;
    const sample = chip.dataset.sample;
    const caption = chip.dataset.caption;
    simulateWhatsAppMessage({ type, text, sample, caption });
  });
});

$('#wa-send-btn')?.addEventListener('click', () => {
  const input = $('#wa-custom-msg');
  if (!input) return;
  const val = input.value.trim();
  if (!val) return;
  input.value = '';
  simulateWhatsAppMessage({ type: 'text', text: val });
});

$('#wa-custom-msg')?.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    $('#wa-send-btn')?.click();
  }
});

// App Download Modal Handlers
const appModal = $('#app-download-modal');
$('#open-app-modal')?.addEventListener('click', () => {
  if (typeof appModal?.showModal === 'function') {
    appModal.showModal();
  } else {
    appModal?.setAttribute('open', 'true');
  }
});

$('#close-app-modal')?.addEventListener('click', () => {
  if (typeof appModal?.close === 'function') {
    appModal.close();
  } else {
    appModal?.removeAttribute('open');
  }
});

appModal?.addEventListener('click', (e) => {
  if (e.target === appModal) {
    if (typeof appModal?.close === 'function') {
      appModal.close();
    } else {
      appModal?.removeAttribute('open');
    }
  }
});
