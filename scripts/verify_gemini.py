"""Phase 0 key check: confirm GEMINI_API_KEY works for both the offline
reasoning model (Flash) and that the Live API model ID is reachable.
Run: python scripts/verify_gemini.py
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("GEMINI_API_KEY")

# Pulled from ai.google.dev/gemini-api/docs/models on 2026-08-14 — re-check
# at AI Studio before demo day, these preview IDs move.
#
# NOTE: gemini-3.1-flash-live-preview is newer but currently broken with
# LiveKit's agents plugin — it rejects send_client_content with a 1007 error
# after the first model turn, which breaks any multi-turn call. Deliberately
# pinned to the 2.5 native-audio model instead. Re-verify this before demo day.
LIVE_MODEL_ID = "gemini-2.5-flash-native-audio-preview-12-2025"
OFFLINE_MODEL_ID = "gemini-2.5-flash"

if not API_KEY:
    print("FAIL: GEMINI_API_KEY not set in .env")
    sys.exit(1)

from google import genai

client = genai.Client(api_key=API_KEY)

# 1. Offline text model — this is what parse_jd/parse_resume/scorer will use.
try:
    resp = client.models.generate_content(
        model=OFFLINE_MODEL_ID,
        contents="Reply with exactly one word: pong",
    )
    print(f"OK  offline model '{OFFLINE_MODEL_ID}' responded: {resp.text.strip()!r}")
except Exception as e:
    print(f"FAIL offline model '{OFFLINE_MODEL_ID}': {e}")
    sys.exit(1)

# 2. Confirm the Live API model ID exists in the account's model list.
try:
    model_ids = [m.name.split("/")[-1] for m in client.models.list()]
    if LIVE_MODEL_ID in model_ids:
        print(f"OK  live model '{LIVE_MODEL_ID}' is listed as available")
    else:
        live_candidates = [m for m in model_ids if "live" in m.lower()]
        print(f"WARN '{LIVE_MODEL_ID}' not found in models.list().")
        print(f"     Live-ish models actually available: {live_candidates}")
except Exception as e:
    print(f"WARN could not list models to confirm live model id: {e}")

print("Gemini key check complete.")
