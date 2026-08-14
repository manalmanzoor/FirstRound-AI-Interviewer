"""wrap_up node: closing remarks, terminal node before END. No interrupt --
the interview is over, nothing left to gate on candidate input."""

import time

from src.graph import InterviewState

NODE_NAME = "wrap_up"
CLOSING = (
    "Thanks so much for your time today -- that's everything on my end. "
    "We'll follow up with next steps soon. Have a great rest of your day!"
)


async def run(state: InterviewState) -> dict:
    now_ms = int(time.time() * 1000)
    turn = {"speaker": "agent", "text": CLOSING, "timestamp_ms": now_ms, "node": NODE_NAME, "interrupted": False}
    return {"transcript": state["transcript"] + [turn]}
