"""AgriPulse Edge: Voice Note Audio Synthesizer (TTS) for illiterate & low-literacy farmers.

Converts local dialect extension guidance into audible voice notes
for playback in Streamlit UI and transmission over WhatsApp.
"""
import io
import math
import struct
from typing import Optional


def synthesize_spoken_audio(text: str, language: str = "en") -> bytes:
    """Synthesizes speech audio bytes using gTTS with instant synthetic WAV fallback."""
    lang_map = {
        "english": "en",
        "pidgin": "en",  # English phonetics with West African prosody
        "hausa": "ha",
        "yoruba": "yo",
    }
    target_lang = lang_map.get(language.lower(), "en")

    try:
        from gtts import gTTS

        buf = io.BytesIO()
        # tld='co.za' or 'com.ng' gives an African English inflection
        tts = gTTS(text=text[:350], lang=target_lang, slow=False, tld="co.za" if target_lang == "en" else "com")
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.getvalue()
    except Exception:
        # Fallback: Generate a clean PCM WAV audio signal so playback never crashes
        return _generate_fallback_audio_wav()


def _generate_fallback_audio_wav(duration_s: float = 1.8, sample_rate: int = 16000) -> bytes:
    """Generates a pleasant melodic chime indicating simulated voice note playback."""
    n_samples = int(duration_s * sample_rate)
    buf = io.BytesIO()

    # WAV header
    # RIFF chunk
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + n_samples * 2))
    buf.write(b"WAVE")
    # fmt chunk
    buf.write(b"fmt ")
    buf.write(struct.pack("<I", 16))
    buf.write(struct.pack("<H", 1))  # PCM
    buf.write(struct.pack("<H", 1))  # mono
    buf.write(struct.pack("<I", sample_rate))
    buf.write(struct.pack("<I", sample_rate * 2))
    buf.write(struct.pack("<H", 2))  # block align
    buf.write(struct.pack("<H", 16)) # bits per sample
    # data chunk
    buf.write(b"data")
    buf.write(struct.pack("<I", n_samples * 2))

    # Two-tone chime (440Hz A4 -> 554.37Hz C#5 -> 659.25Hz E5)
    chord = [440.0, 554.37, 659.25]
    for i in range(n_samples):
        t = i / sample_rate
        decay = math.exp(-2.5 * t)
        val = sum(math.sin(2 * math.pi * f * t) for f in chord) / len(chord)
        sample = int(val * decay * 14000)
        buf.write(struct.pack("<h", max(-32767, min(32767, sample))))

    return buf.getvalue()
