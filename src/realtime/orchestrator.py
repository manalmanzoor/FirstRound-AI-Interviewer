"""Bridges the LangGraph interview state machine (src/graph.py, built and
proven standalone in Phase 3) to the live Gemini Live audio session
(src/realtime/agent.py). This wiring didn't exist before Phase 7 --
Phase 3 tested the graph with scripted text answers, never against a
real voice conversation.

The graph is text-only and headless: it pauses via interrupt() with a
question's text and resumes via Command(resume=answer_text). This
orchestrator is the part that actually SPEAKS each question through the
live session and turns the candidate's spoken answer into the text the
graph expects, using UserInputTranscribedEvent (only fires with
input_audio_transcription enabled on the RealtimeModel -- see agent.py).

setup_interview() is split out and meant to run BEFORE session.start():
a Phase 7 dry run showed our own SQLite-checkpointer-open running
concurrently with Gemini's WebSocket handshake (session.start() kicks
that connection off in the background, it doesn't block on it) --
aiosqlite's connect() and the Gemini handshake's timeout landed within
14ms of each other in the log. On a CPU that has already shown it can
lose timed network handshakes under any concurrent load (the Phase 1
LiveKit room-connect bug), that's not a coincidence worth risking twice.
Doing all of our own file I/O / graph-build / checkpointer-open before
session.start() even begins removes the contention rather than hoping
the timing works out differently next time.
"""

import asyncio
import json
import logging
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command
from livekit.agents import AgentSession

from src.graph import build_graph, make_initial_state

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "interview_checkpoints.db"
logger = logging.getLogger("firstround.orchestrator")


class InterviewSetup:
    def __init__(self, app, checkpointer_cm, candidate, question_plan):
        self.app = app
        self._checkpointer_cm = checkpointer_cm
        self.candidate = candidate
        self.question_plan = question_plan

    async def close(self):
        await self._checkpointer_cm.__aexit__(None, None, None)


async def setup_interview() -> InterviewSetup:
    """Call this BEFORE session.start(). See module docstring for why."""
    candidate = json.loads((ROOT / "output/prep/resume.json").read_text(encoding="utf-8"))
    question_plan = json.loads((ROOT / "output/prep/question_plan.json").read_text(encoding="utf-8"))["questions"]

    builder = build_graph()
    checkpointer_cm = AsyncSqliteSaver.from_conn_string(str(DB_PATH))
    checkpointer = await checkpointer_cm.__aenter__()
    app = builder.compile(checkpointer=checkpointer)

    return InterviewSetup(app, checkpointer_cm, candidate, question_plan)


async def run_interview(session: AgentSession, setup: InterviewSetup, thread_id: str = "real-interview-1") -> None:
    """Call this AFTER session.start(). Runs the actual interview loop
    using the app/checkpointer already prepared by setup_interview()."""
    answer_queue: asyncio.Queue[str] = asyncio.Queue()

    def on_user_transcribed(ev) -> None:
        if ev.is_final and ev.transcript.strip():
            answer_queue.put_nowait(ev.transcript)

    session.on("user_input_transcribed", on_user_transcribed)

    config = {"configurable": {"thread_id": thread_id}}
    initial_state = make_initial_state(setup.candidate, setup.question_plan)
    result = await setup.app.ainvoke(initial_state, config)

    while "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        question_text = payload["text"]
        logger.info(f"[{payload['node']}] asking: {question_text[:80]}")

        await session.generate_reply(
            instructions=(
                "Ask the candidate exactly this question, word-for-word, "
                f"with no paraphrasing and no extra commentary: {question_text!r}"
            )
        )

        # Drain any stale transcripts left over from the question itself
        # being (mis-)attributed to the user, then wait for the real answer.
        while not answer_queue.empty():
            answer_queue.get_nowait()
        answer_text = await answer_queue.get()
        logger.info(f"  candidate answered: {answer_text[:80]}")

        result = await setup.app.ainvoke(Command(resume=answer_text), config)

    final_state = await setup.app.aget_state(config)
    transcript = final_state.values["transcript"]
    if transcript and transcript[-1]["speaker"] == "agent":
        closing_text = transcript[-1]["text"]
        await session.generate_reply(
            instructions=f"Say exactly, word-for-word, with no extra commentary: {closing_text!r}"
        )

    logger.info("Interview complete -- output/transcript.json written by wrap_up node.")
