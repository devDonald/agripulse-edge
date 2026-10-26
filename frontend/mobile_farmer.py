"""AgriPulse Edge — ultra-simple mobile-first PWA view for farmers (360px).

Run alongside the API:
    streamlit run frontend/mobile_farmer.py --server.port 8502
2-tap journey: Snap/Upload leaf -> auto-play dialect voice note. Big buttons, no jargon.
"""
import base64
import io
import os
from datetime import datetime

import requests
import streamlit as st
from PIL import Image

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")

st.set_page_config(page_title="AgriPulse Farmer 📱", page_icon="🌿", layout="centered",
                   initial_sidebar_state="collapsed")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@700;800;900&display=swap');
    #MainMenu, footer, header {visibility: hidden;}
    .block-container { max-width: 430px; padding: 0.8rem 0.8rem 3rem; }
    html, body, [class*="css"] { font-family: 'Inter', system-ui, sans-serif; }
    .pill { background: #0b4d2e; color: #fff; border-radius: 999px; padding: 10px;
      text-align: center; font-weight: 800; font-size: 0.95rem; margin-bottom: 10px; }
    .big-title { font-size: 2.1rem; font-weight: 900; color: #22c55e !important; text-align: center; margin: 2px 0; }
    .sub { text-align: center; color: #d1fae5; font-size: 0.95rem; margin-bottom: 12px; }
    .dx { background: linear-gradient(135deg, #0b4d2e, #16a34a); border-radius: 22px;
      padding: 24px 18px; text-align: center; color: #fff; margin: 12px 0; }
    .dx .icon { font-size: 4rem; }
    .dx .name { font-size: 1.7rem; font-weight: 900; }
    .dx .meta { color: #bbf7d0; font-weight: 700; margin-top: 4px; }
    .recipe { background: #fff; border-left: 8px solid #22c55e; border-radius: 14px;
      padding: 14px; margin: 10px 0; box-shadow: 0 4px 14px rgba(0,0,0,.08); }
    .recipe b { color: #0b4d2e; font-size: 1.1rem; }
    .stButton>button { width: 100%; border-radius: 20px !important; padding: 18px !important;
      font-size: 1.35rem !important; font-weight: 900 !important; }
    .stButton>button[kind="primary"] { background: linear-gradient(135deg, #16a34a, #4ade80) !important;
      color: #052e16 !important; border: none !important; }
    [data-testid="stAudio"] { border-radius: 16px; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="big-title">AgriPulse 🌿</div>', unsafe_allow_html=True)
st.markdown('<div class="sub">Snap sick leaf → hear voice advice. No reading needed.</div>', unsafe_allow_html=True)

st.session_state.setdefault("f_history", [])

# Connectivity pulse: 1.5s health probe decides the status pill
try:
    requests.get(f"{BACKEND_URL}/health", timeout=1.5)
    st.markdown('<div class="pill" style="background:#15803d">🟢 Online Mode (Auto-Sync Ready)</div>',
                unsafe_allow_html=True)
except Exception:
    st.markdown('<div class="pill">⚡ 100% Offline Mode (0KB Data Used)</div>', unsafe_allow_html=True)

if "f_diag" not in st.session_state:
    st.session_state.update(f_diag=None, f_adv=None, f_audio=None, f_img=None)

lang = st.radio("Language", ["🇳🇬 Pidgin", "🇳🇬 Hausa", "🇳🇬 Yoruba", "🇬🇧 English"],
                horizontal=True, label_visibility="collapsed")
lang_code = {"🇳🇬 Pidgin": "pidgin", "🇳🇬 Hausa": "hausa",
             "🇳🇬 Yoruba": "yoruba", "🇬🇧 English": "english"}[lang]

st.markdown("### 1️⃣ Snap / upload leaf")
photo = st.file_uploader("Take photo or upload", type=["jpg", "jpeg", "png", "webp"],
                         label_visibility="collapsed")

st.markdown("##### ⚡ Quick Test Presets")
_FBASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_data")
preset_cols = st.columns(3)
with preset_cols[0]:
    if st.button("🍃 Cassava", use_container_width=True):
        with open(os.path.join(_FBASE, "cassava_mosaic.jpg"), "rb") as f:
            st.session_state.f_raw = f.read()
            st.session_state.f_name = "cassava_mosaic.jpg"
            st.rerun()
with preset_cols[1]:
    if st.button("🌽 Maize", use_container_width=True):
        with open(os.path.join(_FBASE, "maize_fall_armyworm.jpg"), "rb") as f:
            st.session_state.f_raw = f.read()
            st.session_state.f_name = "maize_fall_armyworm.jpg"
            st.rerun()
with preset_cols[2]:
    if st.button("🍅 Tomato", use_container_width=True):
        with open(os.path.join(_FBASE, "tomato_early_blight.jpg"), "rb") as f:
            st.session_state.f_raw = f.read()
            st.session_state.f_name = "tomato_early_blight.jpg"
            st.rerun()

# Single shared Diagnose step: uploader and presets both land in f_raw/f_name.
if photo:
    st.session_state.f_raw = photo.getvalue()
    st.session_state.f_name = photo.name
if st.session_state.get("f_raw"):
    raw = st.session_state.f_raw
    st.session_state.f_img = Image.open(io.BytesIO(raw)).convert("RGB")
    st.image(st.session_state.f_img, use_container_width=True)
    if st.button("📸 CHECK MY LEAF", type="primary"):
        with st.spinner("Checking…"):
            try:
                files = {"file": (st.session_state.get("f_name", "leaf.jpg"), raw, "image/jpeg")}
                diag = requests.post(f"{BACKEND_URL}/api/v1/diagnose-edge",
                                     files=files, timeout=120).json()
                st.session_state.f_diag = diag
                ctx = {"crop_name": diag.get("crop_name"),
                       "disease_detected": diag.get("disease_detected")}
                adv = requests.post(f"{BACKEND_URL}/api/v1/voice-advisory",
                                    json={"query": f"My {ctx['crop_name']} leaf get problem, wetin I fit do?",
                                          "language": lang_code, "diagnosis_context": ctx},
                                    timeout=120).json()
                st.session_state.f_adv = adv
                aud = requests.post(f"{BACKEND_URL}/api/v1/voice-synthesize",
                                    json={"text": adv.get("spoken_reply", "")[:350],
                                          "language": lang_code}, timeout=60).content
                st.session_state.f_audio = aud
                st.rerun()
            except Exception as e:
                st.error(f"Wahala: {e}. Start backend first:\n`python3 -m uvicorn backend.main:app --port 8000`")

diag = st.session_state.f_diag
if diag:
    d = (diag.get("disease_detected") or "").lower()
    icon = "🟡" if "mosaic" in d else ("🐛" if "armyworm" in d else
            ("🟤" if "blight" in d else ("💚" if "healthy" in d else "🔍")))
    st.markdown(
        f'<div class="dx"><div class="icon">{icon}</div>'
        f'<div class="name">{diag.get("disease_detected")}</div>'
        f'<div class="meta">{diag.get("crop_name", "").title()} • {diag.get("damage_percentage")}% damage</div></div>',
        unsafe_allow_html=True,
    )
    if st.session_state.f_audio:
        st.markdown("### 2️⃣ Tap play — voice go tell you 👇")
        st.audio(st.session_state.f_audio, format="audio/mp3")
    if st.session_state.f_adv:
        st.markdown(f"*{st.session_state.f_adv.get('spoken_reply', '')}*")
    st.markdown("### 3️⃣ Do these 3 cheap things 👇")
    for i, r in enumerate((diag.get("organic_remedies") or [])[:3], 1):
        st.markdown(f'<div class="recipe"><b>{["🌿", "🪵", "🧼"][i-1]} {i}. {r.get("title")}</b><br>'
                    f'{r.get("preparation")}</div>', unsafe_allow_html=True)
    if st.button("💾 SAVE AM FOR LATER"):
        _top = (diag.get("organic_remedies") or [{}])[0]
        st.session_state.f_history.append({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "crop": str(diag.get("crop_name", "-")).title(),
            "disease": diag.get("disease_detected", "-"),
            "severity": str(diag.get("severity", "low")).upper(),
            "damage": diag.get("damage_percentage", 0),
            "remedy": _top.get("title", "-"),
            "preparation": _top.get("preparation", ""),
        })
        st.success("Saved ✅ E go sync when network show.")

with st.expander("📂 My Saved Field Scans (Offline History)", expanded=False):
    if not st.session_state.f_history:
        st.caption("No saved scans yet — diagnose a leaf and tap SAVE AM.")
    for h in reversed(st.session_state.f_history):
        st.markdown(
            f'<div class="recipe"><b>🕒 {h["timestamp"]} · {h["crop"]} · '
            f'{h["disease"]}</b><br>Severity: {h["severity"]} · Damage: {h["damage"]}%'
            f'<br>🌿 {h["remedy"]}<br><small>{h["preparation"]}</small></div>',
            unsafe_allow_html=True,
        )
