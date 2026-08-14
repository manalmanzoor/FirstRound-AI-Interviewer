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
import time
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command
from livekit.agents import AgentSession

from src.graph import build_graph, make_initial_state
from src.prompts import load_prompt

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "interview_checkpoints.db"
logger = logging.getLogger("firstround.orchestrator")

# How long the candidate must be quiet before their answer counts as
# finished, on the fast path (VAD agrees they've actually stopped). This
# used to double as the polling interval for the safety extension below
# too, which meant every extra check cost a full 4s even when only ~1s
# of real grace was needed -- that's what made the interview feel like
# it was taking forever between answer and next question. Decoupling the
# two lets the common case (candidate genuinely finished) return fast,
# while the safety margin below still protects against truncation.
ANSWER_SETTLE_S = 2.0

# Once in the safety-extension phase (see collect_full_answer), how often
# to re-check voice/grace state. Fine-grained on purpose -- this is what
# lets the extension end close to when it actually should, instead of
# always overshooting to the next multiple of ANSWER_SETTLE_S.
EXTENSION_POLL_S = 1.0

# Hard ceiling on how long VAD alone can hold the turn open past the
# silence timer, so a stuck "speaking" state can never wedge the
# interview waiting forever.
MAX_EXTRA_WAIT_S = 12.0

# Grace period after the candidate stops speaking, before their answer is
# considered complete. Transcription lags the audio, so text keeps
# arriving after the voice stops; finalising the moment VAD goes quiet
# truncates the tail of the answer.
POST_SPEECH_GRACE_S = 2.5

# Below this many words, a transcript is treated as a noise blip rather
# than an answer, and the orchestrator keeps listening instead of
# advancing the graph. Deliberately low: real short answers do happen
# ("Yes, I did.", "No, we can continue."), and those end in punctuation,
# which is allowed through regardless of length.
MIN_ANSWER_WORDS = 3

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


async def run_interview(
    session: AgentSession,
    setup: InterviewSetup,
    thread_id: str = "real-interview-1",
    room=None,
) -> None:
    """Call this AFTER session.start(). Runs the actual interview loop
    using the app/checkpointer already prepared by setup_interview().

    `room` is optional: when provided, the current graph node is published
    to the candidate's browser over LiveKit's data channel so the UI's
    progress panel reflects the REAL state machine rather than a
    decorative animation. The interview must not depend on it -- any
    failure publishing is swallowed.
    """
    answer_queue: asyncio.Queue[str] = asyncio.Queue()

    async def publish_ui(msg: dict) -> None:
        """Push UI state to the candidate's browser. Best-effort only --
        the interview must never depend on it."""
        if room is None:
            return
        try:
            await room.local_participant.publish_data(
                json.dumps(msg), reliable=True, topic="interview_ui"
            )
        except Exception as e:  # never let UI telemetry break the call
            logger.debug(f"ui publish failed (ignored): {e}")

    async def publish_progress(node: str) -> None:
        await publish_ui({"type": "progress", "node": node})

    async def publish_turn(speaker: str, text: str) -> None:
        """Publish the exact text of a turn. Sourced from the orchestrator
        itself rather than LiveKit transcription events -- we already know
        verbatim what was asked and what came back, so the on-screen
        transcript matches output/transcript.json exactly instead of
        depending on the SDK surfacing transcription reliably."""
        await publish_ui({"type": "turn", "speaker": speaker, "text": text})

    def on_user_transcribed(ev) -> None:
        if ev.is_final and ev.transcript.strip():
            answer_queue.put_nowait(ev.transcript)

    session.on("user_input_transcribed", on_user_transcribed)

    # Actual voice-activity state, straight from the session. A fixed
    # silence timer alone can't tell "finished answering" from "pausing
    # mid-thought" -- introducing yourself naturally has gaps between
    # sentences, and a timer-only approach cut people off after their
    # first sentence. This lets the collector keep waiting while the
    # candidate is genuinely still speaking.
    # Tracks both "are they speaking right now" and "how long since they
    # stopped". The instantaneous flag alone isn't enough: VAD flickers
    # in and out between words and sentences, so a single check at the
    # wrong instant reads as "finished" mid-answer.
    voice = {"speaking": False, "stopped_at": 0.0}

    def on_user_state(ev) -> None:
        speaking = ev.new_state == "speaking"
        if voice["speaking"] and not speaking:
            voice["stopped_at"] = time.monotonic()
        voice["speaking"] = speaking

    session.on("user_state_changed", on_user_state)

    # Gemini Live is an autonomous conversationalist: left alone it will
    # fill a silence with a question of its own. The longer answer-
    # collection window (needed so real answers aren't truncated) is
    # exactly such a silence, so it started inventing off-plan questions
    # -- e.g. asking about supervised vs unsupervised learning, which is
    # nowhere in the question plan. The candidate would answer THAT while
    # the orchestrator was still waiting on its own scripted question,
    # and the two conversations desynced.
    #
    # While the orchestrator is collecting an answer, the agent has no
    # business speaking: everything it should say is driven by the graph.
    # So cut off anything it starts on its own during that window.
    collecting = {"now": False}

    def on_agent_state(ev) -> None:
        if collecting["now"] and ev.new_state == "speaking":
            logger.info("  suppressing unscripted agent speech during answer collection")
            asyncio.create_task(session.interrupt())

    session.on("agent_state_changed", on_agent_state)

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
        await publish_turn("agent", text)
        if verbatim:
            instructions = load_prompt("orchestrator_ask_verbatim").format(text=text)
        else:
            instructions = text
        handle = await session.generate_reply(instructions=instructions)

        # Wait until the question has actually finished playing before we
        # start listening for the answer. Without this the orchestrator
        # was already collecting from the transcript queue WHILE the agent
        # was still speaking, so a stray fragment (echo, a throat-clear,
        # the candidate starting early) could satisfy the answer and the
        # graph would advance to the next question mid-sentence -- the
        # "it asked the next one while I was still answering" bug.
        #
        # This does NOT defeat barge-in: an interruption ends playout
        # early, so wait_for_playout() returns right then and we go
        # straight to listening, which is exactly the desired behaviour.
        try:
            await handle.wait_for_playout()
        except Exception as e:
            logger.debug(f"wait_for_playout failed (continuing): {e}")
        return handle

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
        until the candidate goes quiet for ANSWER_SETTLE_S. If VAD still
        disagrees at that point, switch to fine-grained polling
        (EXTENSION_POLL_S) rather than re-arming the same coarse timeout,
        so the extension ends as soon as it's actually warranted instead
        of always overshooting to the next 2s boundary.
        """
        parts = [await answer_queue.get()]
        poll = ANSWER_SETTLE_S
        extra_waited = 0.0
        while True:
            try:
                nxt = await asyncio.wait_for(answer_queue.get(), timeout=poll)
                parts.append(nxt)
                poll = ANSWER_SETTLE_S
                extra_waited = 0.0
                continue
            except asyncio.TimeoutError:
                pass

            # No new transcript for `poll` seconds -- but that alone
            # doesn't mean they're done. Two things can still be true:
            #   1. VAD says they're speaking right now.
            #   2. They stopped only a moment ago, and transcription runs
            #      BEHIND the audio, so more text is probably still in
            #      flight ("what I say is getting updated late").
            # Hold the turn open for either, up to a hard ceiling -- but
            # poll frequently once we're in this phase, since we're
            # already past the "probably finished" point.
            still_going = voice["speaking"] or (
                time.monotonic() - voice["stopped_at"] < POST_SPEECH_GRACE_S
            )
            if still_going and extra_waited < MAX_EXTRA_WAIT_S:
                extra_waited += poll
                poll = EXTENSION_POLL_S
                continue

            return " ".join(p.strip() for p in parts).strip()

    async def next_candidate_answer(question_text: str) -> str:
        """Wait for a REAL answer.

        Two things are filtered out rather than being treated as answers
        and advancing the graph:
        - "can you repeat that?" -> re-ask the same question
        - noise blips / single stray tokens (e.g. "<noise>", "uh", a
          one-word echo artefact). Advancing on these was part of why the
          interview felt like it moved on before the candidate had
          actually said anything.
        """
        while True:
            answer = await collect_full_answer()
            stripped = answer.strip()

            if is_repeat_request(stripped):
                logger.info(f"  repeat request ({stripped!r}) -- re-asking, not advancing")
                # Re-asking is OUR speech, not the model improvising, so
                # lift the suppression for it -- otherwise on_agent_state
                # would cut off the repeat the candidate just asked for.
                collecting["now"] = False
                try:
                    await ask(question_text)
                finally:
                    collecting["now"] = True
                continue

            if len(stripped.split()) < MIN_ANSWER_WORDS and not stripped.endswith((".", "!", "?")):
                logger.info(f"  ignoring noise fragment {stripped!r} -- still listening")
                continue

            return answer

    while "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        question_text = payload["text"]
        logger.info(f"[{payload['node']}] asking: {question_text[:80]}")
        await publish_progress(payload["node"])

        # ask() now returns only once the question has finished playing
        # (or was interrupted). Draining AFTER that -- rather than before
        # asking -- is what actually clears echo and stray fragments
        # picked up while the agent was talking. Draining beforehand left
        # that whole window unguarded, which is how the graph could
        # advance before the candidate had really answered.
        handle = await ask(question_text)
        if handle is not None and not handle.interrupted:
            while not answer_queue.empty():
                answer_queue.get_nowait()

        # From here until we have the answer, the agent must stay quiet --
        # anything it starts saying on its own gets cut off by
        # on_agent_state above.
        collecting["now"] = True
        try:
            answer_text = await next_candidate_answer(question_text)
        finally:
            collecting["now"] = False
        logger.info(f"  candidate answered: {answer_text[:80]}")
        await publish_turn("candidate", answer_text)

        result = await setup.app.ainvoke(Command(resume=answer_text), config)

    await publish_progress("wrap_up")
    final_state = await setup.app.aget_state(config)
    transcript = final_state.values["transcript"]
    if transcript and transcript[-1]["speaker"] == "agent":
        await ask(transcript[-1]["text"])

    logger.info("Interview complete -- output/transcript.json written by wrap_up node.")
