"""wrap_up node: closing remarks, terminal node before END. No interrupt --
the interview is over, nothing left to gate on candidate input.

Also writes output/transcript.json (PRD section 4 schema) -- this is the
natural point to persist the final record, since the graph state holds
the complete transcript in memory right up to this last turn.
"""

import json
import time
from pathlib import Path

from src.graph import InterviewState

ROOT = Path(__file__).resolve().parents[2]
TRANSCRIPT_PATH = ROOT / "output" / "transcript.json"

NODE_NAME = "wrap_up"
CLOSING = (
    "Thanks so much for your time today -- that's everything on my end. "
    "We'll follow up with next steps soon. Have a great rest of your day!"
)


async def run(state: InterviewState) -> dict:
    now_ms = int(time.time() * 1000)
    turn = {"speaker": "agent", "text": CLOSING, "timestamp_ms": now_ms, "node": NODE_NAME, "interrupted": False}
    final_transcript = state["transcript"] + [turn]

    # "turns" is the PRD-fixed field; guardrail_flags/github_grounded_
    # questions_asked/duration_seconds are extra fields carried over from
    # graph state so src/agents/scorer.py can see them too (PRD section 4:
    # "extra fields OK, missing fields are not") -- without this, the
    # bluff-detection flags gathered live during the interview would have
    # nowhere to go and the scorer would never see them.
    output = {
        "turns": final_transcript,
        "guardrail_flags": state["guardrail_flags"],
        "github_grounded_questions_asked": state["github_grounded_questions_asked"],
        "duration_seconds": state["time_elapsed_s"],
    }

    TRANSCRIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    TRANSCRIPT_PATH.write_text(json.dumps(output, indent=2), encoding="utf-8")

    return {"transcript": final_transcript}
