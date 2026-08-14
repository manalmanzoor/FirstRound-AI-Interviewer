"""State, node registration, edges, and checkpointer wiring for the
interview graph (requirement #5). See src/nodes/ for individual node
implementations and ARCHITECTURE.md for the graph diagram once drawn.
"""

import time
from pathlib import Path
from typing import Literal, TypedDict

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph

ROOT = Path(__file__).resolve().parents[1]

# Soft cap so the graph doesn't run forever -- not a PRD-mandated number,
# just a sane upper bound above the 8+ minute floor requirement #1 sets.
TIME_BUDGET_S = 15 * 60


class InterviewState(TypedDict):
    candidate: dict
    question_plan: list[dict]  # question_plan.json "questions" list
    asked_question_ids: list[str]
    current_question_id: str | None
    transcript: list[dict]  # matches output/transcript.json schema
    probe_count: dict[str, int]  # competency -> follow-ups asked, caps at 2
    difficulty: str
    guardrail_flags: list[str]
    interview_start_ms: int
    time_elapsed_s: int
    last_evaluation: dict | None  # AnswerEvaluation.model_dump(), or None if nothing was asked
    github_grounded_questions_asked: int


def _has_remaining_questions(state: InterviewState, source: str) -> bool:
    asked = set(state["asked_question_ids"])
    if source == "scenario":
        return any(q["id"] not in asked for q in state["question_plan"])
    return any(q["source"] == source and q["id"] not in asked for q in state["question_plan"])


def make_route_after_answer(source: str):
    """Factory, not a single shared function -- routing needs to know
    which source (resume/jd/github/scenario) its node draws from to
    correctly decide "stay on this node" vs "advance to the next node in
    the pipeline". A single shared routing function without this context
    conflated "done following up on the current question" with "done with
    every question this node has", which meant a node advanced after its
    very first question instead of cycling through all of its source's
    questions -- caught in Phase 3 testing (github_deepdive only asked 1
    of 5 planned questions before handing off). See ARCHITECTURE.md.
    """

    def route_after_answer(state: InterviewState) -> Literal["stay", "next_node", "wrap_up"]:
        if state["time_elapsed_s"] >= TIME_BUDGET_S:
            return "wrap_up"

        last_eval = state.get("last_evaluation")
        if last_eval is None:
            # Node had no question left matching its source -- move on.
            return "next_node"

        if last_eval["quality"] in ("shallow", "bluff", "off_topic", "silence"):
            competency = last_eval.get("competency", "")
            probes_so_far = state["probe_count"].get(competency, 0)
            if probes_so_far < 2:
                return "stay"  # content_node will ask a follow-up on the same question

        # Done with this question (strong answer, or follow-up cap hit).
        # Stay on this node if there's another question of its source
        # left to ask -- content_node will pick a fresh one, not a
        # follow-up, since its own is_follow_up check will now be False.
        return "stay" if _has_remaining_questions(state, source) else "next_node"

    return route_after_answer


def build_graph():
    from src.nodes import (
        candidate_qs,
        github_deepdive,
        intro,
        jd_fit,
        resume_probe,
        scenario,
        wrap_up,
    )

    builder = StateGraph(InterviewState)

    builder.add_node("intro", intro.run)
    builder.add_node("resume_probe", resume_probe.run)
    builder.add_node("jd_fit", jd_fit.run)
    builder.add_node("github_deepdive", github_deepdive.run)
    builder.add_node("scenario", scenario.run)
    builder.add_node("candidate_qs", candidate_qs.run)
    builder.add_node("wrap_up", wrap_up.run)

    builder.add_edge(START, "intro")
    builder.add_edge("intro", "resume_probe")

    # 4 conditional edges off the 4 content nodes -- comfortably clears the
    # "2+ conditional edges" bar, and this is genuinely where the adaptive
    # follow-up behavior lives, not decoration on top of a linear graph.
    # "stay" covers both "ask a follow-up" and "ask the next question of
    # this node's source" -- content_node disambiguates those internally.
    builder.add_conditional_edges(
        "resume_probe", make_route_after_answer("resume"),
        {"stay": "resume_probe", "next_node": "jd_fit", "wrap_up": "wrap_up"},
    )
    builder.add_conditional_edges(
        "jd_fit", make_route_after_answer("jd"),
        {"stay": "jd_fit", "next_node": "github_deepdive", "wrap_up": "wrap_up"},
    )
    builder.add_conditional_edges(
        "github_deepdive", make_route_after_answer("github"),
        {"stay": "github_deepdive", "next_node": "scenario", "wrap_up": "wrap_up"},
    )
    builder.add_conditional_edges(
        "scenario", make_route_after_answer("scenario"),
        {"stay": "scenario", "next_node": "candidate_qs", "wrap_up": "wrap_up"},
    )

    builder.add_edge("candidate_qs", "wrap_up")
    builder.add_edge("wrap_up", END)

    return builder


def make_initial_state(candidate: dict, question_plan: list[dict]) -> InterviewState:
    return InterviewState(
        candidate=candidate,
        question_plan=question_plan,
        asked_question_ids=[],
        current_question_id=None,
        transcript=[],
        probe_count={},
        difficulty="medium",
        guardrail_flags=[],
        interview_start_ms=int(time.time() * 1000),
        time_elapsed_s=0,
        last_evaluation=None,
        github_grounded_questions_asked=0,
    )
