"""Phase 0 key check: confirm LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET
work by minting a room-access token and listing rooms on the project.
Run: python scripts/verify_livekit.py
"""
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

URL = os.environ.get("LIVEKIT_URL")
API_KEY = os.environ.get("LIVEKIT_API_KEY")
API_SECRET = os.environ.get("LIVEKIT_API_SECRET")

missing = [n for n, v in [("LIVEKIT_URL", URL), ("LIVEKIT_API_KEY", API_KEY),
                          ("LIVEKIT_API_SECRET", API_SECRET)] if not v]
if missing:
    print(f"FAIL: missing env vars: {missing}")
    sys.exit(1)

from livekit import api


async def main():
    # 1. Token minting is purely local crypto — proves key/secret are well-formed.
    token = (
        api.AccessToken(API_KEY, API_SECRET)
        .with_identity("phase0-check")
        .with_grants(api.VideoGrants(room_join=True, room="phase0-check-room"))
        .to_jwt()
    )
    print(f"OK  minted access token ({len(token)} chars)")

    # 2. Actually round-trip to LiveKit Cloud to prove the URL + creds are live.
    lkapi = api.LiveKitAPI(URL, API_KEY, API_SECRET)
    try:
        rooms = await lkapi.room.list_rooms(api.ListRoomsRequest())
        print(f"OK  connected to {URL} — {len(rooms.rooms)} room(s) currently active")
    finally:
        await lkapi.aclose()

    print("LiveKit key check complete.")


asyncio.run(main())
