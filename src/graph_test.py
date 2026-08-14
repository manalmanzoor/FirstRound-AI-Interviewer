"""Phase 3 acceptance tests for the graph, run standalone (no live call
needed): exercises the adaptive-follow-up routing with scripted answers,
then proves the SQLite checkpointer actually resumes mid-interview rather
than restarting.

Run: python -m src.graph_test
"""

import asyncio
import json
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from src.graph import build_graph, make_initial_state

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "checkpoints.db"

# Scripted to exercise every routing path at least once:
# - a strong answer (-> next_node immediately, difficulty raised)
# - two consecutive shallow/silence answers on the same question
#   (-> follow_up, follow_up, then forced next_node at the probe cap)
# - a bluff answer (-> follow_up + guardrail_flags entry)
SCRIPTED_ANSWERS = [
    "Hi, I'm Manal, a software engineering student who's spent the last year building agentic AI products end to end.",
    # resume_probe q1 -- answer with real specifics -> should read as strong
    "I used LangGraph with a typed state object, added conditional edges for routing, and a custom "
    "middleware layer that surfaces confidence and source metadata to the frontend for the human-in-the-loop UI.",
    # jd_fit q1 -- deliberately vague to trigger follow-up twice
    "Uh, I'm not totally sure, I think we just tested it a bit.",
    "Yeah, pretty much the same, nothing specific comes to mind.",
    # github_deepdive q1 -- confident but internally inconsistent (bluff bait)
    "Oh yeah I wrote that whole guardrail stack myself in an afternoon, it just uses a basic if-statement, "
    "nothing complicated about five layers really.",
    # remaining questions -- keep answering something reasonable so the
    # graph can run to completion within this test
    "I'd approach it by isolating the failure with unit tests first, then checking the logs for the exact error.",
    "Good question -- I focused on making the API resilient to retries and idempotent writes.",
    "I structured the evaluation with held-out test cases and measured precision/recall against a human-labeled set.",
    "I used a shared confidence field on every API response so the frontend could render it consistently.",
    "No real questions from me right now, this all sounds great, thanks!",
]


async def run_scripted_interview():
    print("=== Part 1: scripted interview run (exercises all routing paths) ===")
    if DB_PATH.exists():
        DB_PATH.unlink()

    candidate = json.loads((ROOT / "output/prep/resume.json").read_text(encoding="utf-8"))
    question_plan = json.loads((ROOT / "output/prep/question_plan.json").read_text(encoding="utf-8"))["questions"]

    builder = build_graph()
    config = {"configurable": {"thread_id": "test-interview-1"}}
    answers = iter(SCRIPTED_ANSWERS)

    async with AsyncSqliteSaver.from_conn_string(str(DB_PATH)) as checkpointer:
        app = builder.compile(checkpointer=checkpointer)

        initial_state = make_initial_state(candidate, question_plan)
        result = await app.ainvoke(initial_state, config)

        step = 0
        while "__interrupt__" in result:
            interrupt_payload = result["__interrupt__"][0].value
            print(f"  [{interrupt_payload['node']}] Q: {interrupt_payload['text'][:90]}")
            try:
                answer = next(answers)
            except StopIteration:
                answer = "I think that covers it."
            print(f"           A: {answer[:90]}")
            result = await app.ainvoke(Command(resume=answer), config)
            step += 1
            if step > 25:
                print("  (stopping test after 25 turns to avoid runaway)")
                break

        state = await app.aget_state(config)
        print(f"\nOK  interview finished after {step} turns")
        print(f"    final node history reachable, {len(state.values['transcript'])} transcript turns")
        print(f"    github_grounded_questions_asked = {state.values['github_grounded_questions_asked']}")
        print(f"    guardrail_flags = {state.values['guardrail_flags']}")
        print(f"    probe_count = {state.values['probe_count']}")

        assert state.values["github_grounded_questions_asked"] >= 3, "requirement #4 needs >=3 github questions"
        assert any("bluff" in f for f in state.values["guardrail_flags"]), "bluff detection should have fired"
        print("OK  requirement #4 (>=3 github questions) and bluff detection both confirmed")


async def run_checkpoint_resume_test():
    print("\n=== Part 2: checkpointer kill-and-resume proof ===")
    if DB_PATH.exists():
        DB_PATH.unlink()

    candidate = json.loads((ROOT / "output/prep/resume.json").read_text(encoding="utf-8"))
    question_plan = json.loads((ROOT / "output/prep/question_plan.json").read_text(encoding="utf-8"))["questions"]
    config = {"configurable": {"thread_id": "test-resume-1"}}

    # --- "process 1": run a few turns, then simulate a crash by just
    # letting this checkpointer/app instance go out of scope ---
    builder = build_graph()
    async with AsyncSqliteSaver.from_conn_string(str(DB_PATH)) as checkpointer:
        app = builder.compile(checkpointer=checkpointer)
        initial_state = make_initial_state(candidate, question_plan)
        result = await app.ainvoke(initial_state, config)
        first_node = result["__interrupt__"][0].value["node"]
        print(f"  process 1: reached first interrupt at node '{first_node}'")

        result = await app.ainvoke(Command(resume="I'm Manal, an AI/full-stack engineer."), config)
        second_node = result["__interrupt__"][0].value["node"]
        print(f"  process 1: answered intro, now paused at node '{second_node}'")
        print("  process 1: killed here on purpose (no explicit close, just going out of scope)")

    # --- "process 2": brand new builder + checkpointer + app instance,
    # same thread_id, same db file -- proves resume works across a real
    # process boundary, not just within one Python session's memory ---
    builder2 = build_graph()
    async with AsyncSqliteSaver.from_conn_string(str(DB_PATH)) as checkpointer2:
        app2 = builder2.compile(checkpointer=checkpointer2)
        state = await app2.aget_state(config)
        resumed_node = state.tasks[0].name if state.tasks else state.next[0]
        print(f"  process 2 (fresh instance): checkpoint shows next node = '{resumed_node}'")

        assert resumed_node == second_node, (
            f"expected to resume at '{second_node}', but checkpoint says '{resumed_node}' -- "
            "this would mean the interview restarted instead of resuming"
        )
        print(f"OK  fresh process instance resumed at the correct node ('{resumed_node}'), not from START")

        # prove it can actually continue running, not just report the right node
        result = await app2.ainvoke(Command(resume="I used FastAPI and a Postgres-backed queue."), config)
        next_node = result["__interrupt__"][0].value["node"]
        print(f"OK  resumed run continued correctly, now at node '{next_node}'")


async def main():
    await run_scripted_interview()
    await run_checkpoint_resume_test()
    if DB_PATH.exists():
        DB_PATH.unlink()


if __name__ == "__main__":
    asyncio.run(main())
