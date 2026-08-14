"""Shared implementation behind resume_probe/jd_fit/github_deepdive/
scenario -- they differ only in which question `source` they draw from
and their node name, so one real implementation backs all four thin node
files rather than four copies of the same logic.
"""

import asyncio
import time

from langgraph.types import interrupt

from src.agents.answer_evaluator import evaluate_answer
from src.graph import InterviewState
from src.guardrails.banned_questions import check_question

GENERIC_FOLLOW_UP = "Can you go a bit deeper on that -- what specifically did you do, and why that approach?"


def _next_question(state: InterviewState, source: str) -> tuple[dict | None, list[str], list[str]]:
    """Returns (question, skipped_ids, guardrail_flags). Banned-topic
    questions are filtered out here -- guardrail #9a, checked BEFORE the
    question ever reaches the candidate, not after. Skipped ids are
    reported back so the caller marks them "asked" too (otherwise
    _next_question would keep re-skipping, and re-flagging, the same
    banned question every single time it's called)."""
    asked = set(state["asked_question_ids"])
    if source == "scenario":
        # scenario is a catch-all for whatever's left, regardless of source --
        # the question plan schema (PRD section 4) only has github/resume/jd
        # sources, no dedicated "scenario" bucket. See ARCHITECTURE.md.
        candidates = [q for q in state["question_plan"] if q["id"] not in asked]
    else:
        candidates = [q for q in state["question_plan"] if q["source"] == source and q["id"] not in asked]

    skipped_ids, flags = [], []
    for q in candidates:
        result = check_question(q["text"])
        if not result.blocked:
            return q, skipped_ids, flags
        skipped_ids.append(q["id"])
        flags.append(f"banned_topic_blocked:{q['id']}:{result.topic}")
    return None, skipped_ids, flags


def _elapsed_s(state: InterviewState) -> int:
    return int(time.time() * 1000 - state["interview_start_ms"]) // 1000


async def content_node(state: InterviewState, *, node_name: str, source: str) -> dict:
    elapsed = _elapsed_s(state)
    last_eval = state.get("last_evaluation")
    current_id = state.get("current_question_id")

    # Must mirror route_after_answer's predicate exactly -- that function
    # decided to loop back here precisely because this was true. Checking
    # `current_id not in asked_question_ids` here was the original (buggy)
    # approach: asked_question_ids gets the id added the moment it's first
    # asked (see below), so on the very next loop-back that membership
    # check already read False, silently turning every "follow_up" routing
    # decision into "ask a new question instead" -- probe_count never
    # incremented, the adaptive follow-up never actually happened despite
    # the routing looking correct in isolation.
    is_follow_up = False
    if current_id is not None and last_eval is not None:
        current_question = next((q for q in state["question_plan"] if q["id"] == current_id), None)
        if current_question and last_eval["quality"] in ("shallow", "bluff", "off_topic", "silence"):
            probes_so_far = state["probe_count"].get(current_question["competency"], 0)
            is_follow_up = probes_so_far < 2

    skipped_ids: list[str] = []
    skip_flags: list[str] = []
    if is_follow_up:
        question = next(q for q in state["question_plan"] if q["id"] == current_id)
        idx = state["probe_count"].get(question["competency"], 0)
        triggers = question.get("follow_up_triggers", [])
        candidate_text = triggers[idx] if idx < len(triggers) else GENERIC_FOLLOW_UP
        # Guardrail #9a applies to follow-ups too, not just planned
        # questions -- fall back to the fixed, pre-reviewed generic text
        # if a generated follow-up trigger somehow touches a banned topic.
        text = GENERIC_FOLLOW_UP if check_question(candidate_text).blocked else candidate_text
    else:
        question, skipped_ids, skip_flags = _next_question(state, source)
        if question is None:
            # Nothing left for this node's source -- signal "move on"
            # without asking anything (route_after_answer reads
            # last_evaluation=None as "advance").
            return {
                "time_elapsed_s": elapsed,
                "last_evaluation": None,
                "current_question_id": None,
                "asked_question_ids": state["asked_question_ids"] + skipped_ids,
                "guardrail_flags": state["guardrail_flags"] + skip_flags,
            }
        text = question["text"]

    now_ms = int(time.time() * 1000)
    ask_turn = {"speaker": "agent", "text": text, "timestamp_ms": now_ms, "node": node_name, "interrupted": False}

    answer_text = interrupt({"node": node_name, "question_id": question["id"], "text": text})

    answer_ms = int(time.time() * 1000)
    answer_turn = {
        "speaker": "candidate", "text": answer_text, "timestamp_ms": answer_ms,
        "node": node_name, "interrupted": False,
    }

    # MUST stay off the event loop. evaluate_answer() -> gemini.structured()
    # is a synchronous, blocking HTTP call, and on a rate-limit retry it
    # also does time.sleep(up to 60s). Awaited directly inside the live
    # agent's event loop it froze everything -- including the Gemini Live
    # WebSocket's keepalive pings, which the server then dropped with
    # "1011 keepalive ping timeout / 1006 abnormal closure", killing the
    # interview mid-call. Found by reading the logs of a real interview
    # that died after the intro question.
    evaluation = await asyncio.to_thread(
        evaluate_answer, text, answer_text, question["competency"]
    )
    eval_dict = evaluation.model_dump()
    eval_dict["competency"] = question["competency"]

    updates: dict = {
        "transcript": state["transcript"] + [ask_turn, answer_turn],
        "last_evaluation": eval_dict,
        "current_question_id": question["id"],
        "time_elapsed_s": _elapsed_s(state),
    }

    if is_follow_up:
        new_count = state["probe_count"].get(question["competency"], 0) + 1
        updates["probe_count"] = {**state["probe_count"], question["competency"]: new_count}
    else:
        updates["asked_question_ids"] = state["asked_question_ids"] + skipped_ids + [question["id"]]
        if question["source"] == "github":
            updates["github_grounded_questions_asked"] = state["github_grounded_questions_asked"] + 1
        if evaluation.quality == "strong":
            updates["difficulty"] = "hard"

    # Both guardrail sources (skipped banned-topic questions this turn,
    # and a bluff detected in the answer just evaluated) accumulate onto
    # the SAME list here -- two separate `state["guardrail_flags"] + [...]`
    # assignments would silently overwrite each other instead of both
    # landing, since both would start from the same pre-update state.
    new_flags = list(skip_flags)
    if evaluation.quality == "bluff":
        new_flags.append(f"possible_bluff:{question['id']}:{evaluation.reasoning[:120]}")
    if new_flags:
        updates["guardrail_flags"] = state["guardrail_flags"] + new_flags

    return updates
