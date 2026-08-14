"""Phase 4 acceptance test for the HITL gate (requirement #7): proves the
graph genuinely pauses and that approve/edit/reject all functionally
work, without needing a real terminal for input() (src/hitl.py's
interactive CLI is the real one a human uses; this drives the same
underlying graph with scripted decisions instead).

Run: python -m src.hitl_test
"""

import asyncio
import copy
import json
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from src.hitl import build_hitl_graph

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "hitl_test_checkpoints.db"

SAMPLE_PLAN = {
    "questions": [
        {"id": "q1", "text": "Original question text", "competency": "technical_depth",
         "source": "github", "source_reference": "org/repo/file.py", "difficulty": "medium",
         "follow_up_triggers": []},
        {"id": "q2", "text": "Another original question", "competency": "system_design",
         "source": "resume", "source_reference": "resume line", "difficulty": "medium",
         "follow_up_triggers": []},
    ],
    "approved_by_human": False,
    "edits_made": [],
}


async def run_one(thread_id: str, decision: dict) -> dict:
    if DB_PATH.exists():
        DB_PATH.unlink()
    builder = build_hitl_graph()
    config = {"configurable": {"thread_id": thread_id}}

    async with AsyncSqliteSaver.from_conn_string(str(DB_PATH)) as checkpointer:
        app = builder.compile(checkpointer=checkpointer)
        plan = copy.deepcopy(SAMPLE_PLAN)
        result = await app.ainvoke({"question_plan": plan, "decision": None}, config)

        assert "__interrupt__" in result, "graph did not pause -- HITL gate isn't actually gating anything"
        payload = result["__interrupt__"][0].value
        assert payload["question_count"] == 2

        final = await app.ainvoke(Command(resume=decision), config)
    return final["question_plan"]


async def main():
    print("=== approve ===")
    plan = await run_one("hitl-approve", {"action": "approve"})
    assert plan["approved_by_human"] is True
    assert plan["edits_made"] == []
    assert plan["questions"][0]["text"] == "Original question text"
    print(f"OK  approved_by_human={plan['approved_by_human']}, edits_made={plan['edits_made']}")

    print("\n=== edit ===")
    plan = await run_one("hitl-edit", {"action": "edit", "edits": {"q1": "Edited question text"}})
    assert plan["approved_by_human"] is True
    assert plan["questions"][0]["text"] == "Edited question text"
    assert plan["questions"][1]["text"] == "Another original question"  # untouched
    assert len(plan["edits_made"]) == 1
    print(f"OK  q1 text changed, q2 untouched, edits_made={plan['edits_made']}")

    print("\n=== reject ===")
    plan = await run_one("hitl-reject", {"action": "reject", "reason": "questions too generic"})
    assert plan["approved_by_human"] is False
    assert "rejected" in plan["edits_made"][0]
    print(f"OK  approved_by_human={plan['approved_by_human']}, edits_made={plan['edits_made']}")

    print("\nOK  all three HITL actions (approve/edit/reject) proven to work, graph genuinely paused each time")
    DB_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(main())
