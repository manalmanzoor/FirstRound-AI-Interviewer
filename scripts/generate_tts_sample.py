"""Generates a real TTS audio clip to test web/avatar.html against --
concrete proof the lip-sync works against actual TTS audio (requirement
#1), not just a sine wave.

Run: python scripts/generate_tts_sample.py
"""

import os
import wave
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "web" / "sample_tts.wav"

TEXT = (
    "Hi, thanks for joining. I'm the AI interviewer for the Junior AI Engineer "
    "role at Northwind Labs. To start, could you introduce yourself and give "
    "a quick overview of your background?"
)

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

response = client.models.generate_content(
    model="gemini-2.5-flash-preview-tts",
    contents=TEXT,
    config=types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck")
            )
        ),
    ),
)

pcm_data = response.candidates[0].content.parts[0].inline_data.data

with wave.open(str(OUT_PATH), "wb") as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)  # 16-bit PCM
    wf.setframerate(24000)  # Gemini TTS output rate
    wf.writeframes(pcm_data)

print(f"OK  wrote {OUT_PATH} ({len(pcm_data)} bytes of PCM audio)")
