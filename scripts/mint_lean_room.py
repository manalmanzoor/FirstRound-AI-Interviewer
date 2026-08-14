"""Mints a join token for a fresh interview room.

Deliberately does NOT create an agent dispatch. src/realtime/agent.py
registers with automatic dispatch (no agent_name), so LiveKit assigns the
agent when the candidate actually joins the room. Pre-dispatching was the
cause of a long-running "the interviewer never speaks" problem: the agent
would join an empty room immediately, then hit its ~5 minute entrypoint
timeout waiting for a candidate who hadn't clicked the link yet, leaving
a dead room behind. With automatic dispatch the link stays valid until
it's used.

Run: python scripts/mint_lean_room.py
"""

import os
import time

from dotenv import load_dotenv
from livekit import api

load_dotenv()

URL = os.environ["LIVEKIT_URL"]
API_KEY = os.environ["LIVEKIT_API_KEY"]
API_SECRET = os.environ["LIVEKIT_API_SECRET"]

ROOM_NAME = f"firstround-{int(time.time())}"
IDENTITY = "candidate"

token = (
    api.AccessToken(API_KEY, API_SECRET)
    .with_identity(IDENTITY)
    .with_name("Candidate")
    .with_grants(api.VideoGrants(room_join=True, room=ROOM_NAME))
    .to_jwt()
)

print(f"Room:  {ROOM_NAME}")
print(f"URL:   {URL}")
print("\nThe agent auto-joins when you open this link (no pre-dispatch,")
print("so it will not go stale while you get ready):\n")
print(
    f"file:///C:/Users/abdullah/Desktop/AI-Interviewer/web/join.html"
    f"?url={URL}&token={token}&room={ROOM_NAME}"
)
