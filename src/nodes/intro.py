"""intro node: greets the candidate and asks them to introduce themselves.
Unconditional edge to resume_probe -- no adaptive routing here, that
starts once real technical content begins."""

import time

from langgraph.types import interrupt

from src.graph import InterviewState

NODE_NAME = "intro"
GREETING = (
    "Hi, thanks for joining. I'm the AI interviewer for the Junior AI "
    "Engineer role at Northwind Labs. To start, could you introduce "
    "yourself and give a quick overview of your background?"
)


async def run(state: InterviewState) -> dict:
    now_ms = int(time.time() * 1000)
    ask_turn = {"speaker": "agent", "text": GREETING, "timestamp_ms": now_ms, "node": NODE_NAME, "interrupted": False}

    answer_text = interrupt({"node": NODE_NAME, "question_id": None, "text": GREETING})

    answer_ms = int(time.time() * 1000)
    answer_turn = {
        "speaker": "candidate", "text": answer_text, "timestamp_ms": answer_ms,
        "node": NODE_NAME, "interrupted": False,
    }

    return {"transcript": state["transcript"] + [ask_turn, answer_turn]}
