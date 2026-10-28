const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
let diagnosis = null;
let advisory = null;

function toast(message, error = false) {
  const el = $('#toast'); el.textContent = message; el.className = `toast show${error ? ' error' : ''}`;
  setTimeout(() => el.classList.remove('show'), 3600);
}

function showView(name) {
  $$('.app-view').forEach((v) => v.classList.toggle('active', v.id === name));
  $$('.side-link').forEach((b) => b.classList.toggle('active', b.dataset.view === name));
  $('#view-title').textContent = ({clinic:'Crop clinic', command:'Command center', history:'Field records', models:'Model health'})[name];
  document.body.classList.remove('nav-open');
}
$$('.side-link').forEach((b) => b.addEventListener('click', () => showView(b.dataset.view)));
$('.mobile-nav').addEventListener('click', () => document.body.classList.toggle('nav-open'));
const requested = new URLSearchParams(location.search).get('mode');
if (requested === 'command') showView('command');

const fileInput = $('#leaf-file');
fileInput.addEventListener('change', () => {
  const file = fileInput.files[0]; if (!file) return;
  if (file.size > 10 * 1024 * 1024) { toast('Please choose an image smaller than 10MB.', true); fileInput.value=''; return; }
  const url = URL.createObjectURL(file); $('#preview').src = url; $('#result-image').src = url;
  $('#drop-zone').classList.add('has-image'); $('#diagnose').disabled = false;
});

$('#diagnose').addEventListener('click', async () => {
  const file = fileInput.files[0]; if (!file) return;
  const button = $('#diagnose'); button.disabled = true; button.classList.add('loading'); button.querySelector('span').textContent = 'Analysing symptoms…';
  const form = new FormData(); form.append('file', file);
  const edge = $('#analysis-mode').value === 'edge';
  try {
    const response = await fetch(edge ? '/api/v1/diagnose-edge' : '/api/v1/diagnose', {method:'POST', body:form});
    if (!response.ok) throw new Error((await response.json()).detail || 'Diagnosis failed');
    diagnosis = await response.json();
    // Feed web diagnoses into the same field record stream used by mobile and WhatsApp.
    await fetch('/api/v1/mobile/sync', {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({farmer_id:'web-field-team', client_scan_id:`web-${Date.now()}`,
        crop_name:diagnosis.crop_name, disease_detected:diagnosis.disease_detected,
        damage_percentage:diagnosis.damage_percentage, severity:diagnosis.severity,
        language:$('#language').value, timestamp:new Date().toISOString()})}).catch(()=>null);
    const ctx = {crop_name:diagnosis.crop_name, disease_detected:diagnosis.disease_detected, damage_percentage:diagnosis.damage_percentage, severity:diagnosis.severity};
    const advRes = await fetch('/api/v1/voice-advisory', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({query:`What should I do about ${diagnosis.disease_detected} on my ${diagnosis.crop_name}?`, language:$('#language').value, diagnosis_context:ctx})});
    if (advRes.ok) advisory = await advRes.json();
    renderDiagnosis(); toast('Diagnosis complete. Treatment guidance is ready.');
  } catch (err) { toast(err.message || 'Could not complete the diagnosis.', true); }
  finally { button.disabled = false; button.classList.remove('loading'); button.querySelector('span').textContent = 'Analyse crop photo'; }
});

function renderDiagnosis() {
  $('#result-disease').textContent = diagnosis.disease_detected || 'Condition detected';
  const engine = diagnosis.segmentation?.method_used || diagnosis.model_used || 'AgriPulse ensemble';
  $('#result-crop').textContent = `${diagnosis.crop_name || 'Crop'} · ${Math.round((diagnosis.confidence || 0) * 100)}% confidence · ${engine}`;
  $('#result-damage').textContent = `${Math.round(diagnosis.damage_percentage || 0)}%`;
  $('#result-severity').textContent = diagnosis.severity || 'Review';
  if (diagnosis.segmentation?.mask_overlay_base64) {
    $('#result-image').src = `data:image/png;base64,${diagnosis.segmentation.mask_overlay_base64}`;
  }
  const remedies = diagnosis.organic_remedies || [];
  $('#remedies').innerHTML = remedies.slice(0,3).map((r,i) => `<div class="remedy"><i>${i+1}</i><div><b>${r.title || 'Treatment step'}</b><p>${r.preparation || r.description || ''}</p></div></div>`).join('') || '<p>Review the voice guidance for next steps.</p>';
  $('#result-panel').hidden = false; $('#result-panel').scrollIntoView({behavior:'smooth', block:'start'});
}

$('#play-advice').addEventListener('click', async () => {
  if (!advisory?.spoken_reply) return toast('Voice guidance is not available for this result.', true);
  try { const res = await fetch('/api/v1/voice-synthesize', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({text:advisory.spoken_reply.slice(0,500), language:$('#language').value})}); if(!res.ok) throw new Error('Audio generation failed'); const url=URL.createObjectURL(await res.blob()); const audio=$('#advice-audio'); audio.src=url; await audio.play(); } catch(err) { toast(err.message, true); }
});

$('#load-history').addEventListener('click', async () => { try { const r=await fetch('/api/v1/mobile/history?farmer_id=anonymous&limit=20'); const d=await r.json(); const rows=d.scans || d.history || (Array.isArray(d)?d:[]); $('#history-list').innerHTML = rows.length ? rows.map(x=>`<div class="data-row"><b>${x.crop_name || 'Crop'}</b><span>${x.disease_detected || 'Diagnosis'} · ${x.damage_percentage || 0}% damage</span></div>`).join('') : '<p class="muted">No synced records yet.</p>'; } catch(e){toast('Could not load field records.',true)} });
$('#load-models').addEventListener('click', async () => { try { const r=await fetch('/api/v1/models'); const d=await r.json(); $('#model-list').innerHTML=(d.models||[]).map(x=>`<div class="data-row"><b>${x.label || x.name || x.id}</b><span>${x.purpose || x.description || 'Available'}</span></div>`).join(''); } catch(e){toast('Could not load the model catalog.',true)} });
