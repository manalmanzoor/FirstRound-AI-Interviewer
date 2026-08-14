"""candidate_qs node: invites the candidate to ask questions before
wrap-up. Unconditional edge to wrap_up."""

import time

from langgraph.types import interrupt

from src.graph import InterviewState

NODE_NAME = "candidate_qs"
PROMPT = "That covers what I wanted to ask. Do you have any questions for me about the role or the team?"


async def run(state: InterviewState) -> dict:
    now_ms = int(time.time() * 1000)
    ask_turn = {"speaker": "agent", "text": PROMPT, "timestamp_ms": now_ms, "node": NODE_NAME, "interrupted": False}

    answer_text = interrupt({"node": NODE_NAME, "question_id": None, "text": PROMPT})

    answer_ms = int(time.time() * 1000)
    answer_turn = {
        "speaker": "candidate", "text": answer_text, "timestamp_ms": answer_ms,
        "node": NODE_NAME, "interrupted": False,
    }

    return {"transcript": state["transcript"] + [ask_turn, answer_turn]}
