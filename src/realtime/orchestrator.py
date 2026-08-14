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

from . import _compat  # noqa: F401  -- MUST precede any livekit.agents import

import asyncio
import json
import logging
import re
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command
from livekit.agents import AgentSession

from src.graph import build_graph, make_initial_state

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "interview_checkpoints.db"
logger = logging.getLogger("firstround.orchestrator")

# How long the candidate must be quiet before their answer counts as
# finished. Long enough to survive a mid-sentence breath or a pause to
# think, short enough that the interview doesn't feel laggy.
ANSWER_SETTLE_S = 2.5

# A candidate asking us to repeat is NOT an answer -- feeding it to the
# graph as one burns a real question and (worse) counts toward the
# adaptive-follow-up probe cap. Seen for real in the first interview:
# "Can you repeat again?" and "Uh, what were you asking?" both got
# recorded as answers and the graph moved on.
# Leading filler is common in real speech and broke the first version of
# this pattern: the two phrases actually said in the first interview
# ("Can you repeat again?", "Uh, what were you asking?") both slipped
# through an over-rigid regex. Allow filler prefixes, and allow trailing
# words after the key phrase rather than anchoring straight to the end.
_FILLER = r"(?:(?:uh+|um+|er+|ah+|sorry|hey|wait|hold on|so)[\s,]+)*"
_REPEAT_REQUEST = re.compile(
    rf"^\s*{_FILLER}("
    r"(can|could|would) you (please )?(repeat|say)\b[\w\s']*"
    r"|repeat\b[\w\s']*"
    r"|what (was|were) (you|the) (asking|question|saying|said)\b[\w\s']*"
    r"|come again"
    r"|i (didn'?t|did not) (catch|hear|get)\b[\w\s']*"
    r"|pardon( me)?"
    r"|say (that |it )?again"
    r")[\s?.!]*$",
    re.IGNORECASE,
)


def is_repeat_request(text: str) -> bool:
    return bool(_REPEAT_REQUEST.match(text.strip()))


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

    async def ask(text: str, *, verbatim: bool = True) -> None:
        """Speak `text` through the live session, suppressing Gemini's own
        spontaneous reply first.

        Gemini Live is a full conversational agent: when it detects the
        candidate finished speaking it generates its OWN response, while
        this orchestrator is separately driving the conversation with the
        scripted next question. Both play at once -- the "two voices
        saying different things" reported in the first real interview.
        interrupt() cancels whatever Gemini started on its own before we
        say what the graph actually wants asked.
        """
        await session.interrupt()
        if verbatim:
            instructions = (
                "Ask the candidate exactly this question, word-for-word, "
                f"with no paraphrasing and no extra commentary: {text!r}"
            )
        else:
            instructions = text
        await session.generate_reply(instructions=instructions)

    async def collect_full_answer() -> str:
        """Gather ONE complete spoken answer, not just its first fragment.

        Gemini emits several is_final segments for a single continuous
        utterance -- one sentence, several events. Taking the first as
        "the answer" made the agent ask the next question while the
        candidate was still mid-sentence, and their remaining words then
        landed as the answer to that next question. In the first real
        interview "my name is Manal and I'm a software engineering
        student / I've spent the last year building AI projects..." got
        split across two different questions exactly this way.

        So: take the first segment, then keep absorbing further segments
        until the candidate goes quiet for ANSWER_SETTLE_S.
        """
        parts = [await answer_queue.get()]
        while True:
            try:
                nxt = await asyncio.wait_for(answer_queue.get(), timeout=ANSWER_SETTLE_S)
            except asyncio.TimeoutError:
                return " ".join(p.strip() for p in parts).strip()
            parts.append(nxt)

    async def next_candidate_answer(question_text: str) -> str:
        """Wait for a real answer, transparently handling "can you repeat
        that?" by re-asking instead of treating it as the answer."""
        while True:
            answer = await collect_full_answer()
            if is_repeat_request(answer):
                logger.info(f"  repeat request ({answer.strip()!r}) -- re-asking, not advancing")
                await ask(question_text)
                continue
            return answer

    while "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        question_text = payload["text"]
        logger.info(f"[{payload['node']}] asking: {question_text[:80]}")

        # Drain stale transcripts BEFORE asking, so anything captured while
        # the previous turn was settling can't be mistaken for the answer
        # to the question we're about to ask.
        while not answer_queue.empty():
            answer_queue.get_nowait()

        await ask(question_text)
        answer_text = await next_candidate_answer(question_text)
        logger.info(f"  candidate answered: {answer_text[:80]}")

        result = await setup.app.ainvoke(Command(resume=answer_text), config)

    final_state = await setup.app.aget_state(config)
    transcript = final_state.values["transcript"]
    if transcript and transcript[-1]["speaker"] == "agent":
        await ask(transcript[-1]["text"])

    logger.info("Interview complete -- output/transcript.json written by wrap_up node.")
