"""Creates a room + agent dispatch WITHOUT recording enabled, and mints a
participant token -- testing whether the LiveKit Console's default
enable_recording=true was adding enough overhead to tip the room-connect
race against the ~20s FFI timeout (see ARCHITECTURE.md Phase 1).

Run: python scripts/mint_lean_room.py
"""

import asyncio
import os
import time

from dotenv import load_dotenv
from livekit import api

load_dotenv()

URL = os.environ["LIVEKIT_URL"]
API_KEY = os.environ["LIVEKIT_API_KEY"]
API_SECRET = os.environ["LIVEKIT_API_SECRET"]

ROOM_NAME = f"firstround-lean-{int(time.time())}"
AGENT_NAME = "firstround-interviewer"
IDENTITY = "lean-test-participant"


async def main():
    lkapi = api.LiveKitAPI(URL, API_KEY, API_SECRET)
    try:
        dispatch = await lkapi.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(agent_name=AGENT_NAME, room=ROOM_NAME)
        )
        print(f"OK  dispatched agent -> room '{ROOM_NAME}' (dispatch id: {dispatch.id}, no recording requested)")
    finally:
        await lkapi.aclose()

    token = (
        api.AccessToken(API_KEY, API_SECRET)
        .with_identity(IDENTITY)
        .with_name("Lean Test")
        .with_grants(api.VideoGrants(room_join=True, room=ROOM_NAME))
        .to_jwt()
    )

    print(f"\nRoom:  {ROOM_NAME}")
    print(f"URL:   {URL}")
    print(f"Token: {token}")
    print(f"\nOpen web/join.html and paste the URL + token above, or open this link:")
    print(f"file:///C:/Users/abdullah/Desktop/AI-Interviewer/web/join.html?url={URL}&token={token}&room={ROOM_NAME}")


asyncio.run(main())
