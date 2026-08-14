"""Live LiveKit call with a Gemini Live voice agent, driving the real
LangGraph interview state machine (src/graph.py) via src/realtime/orchestrator.py.

Barge-in is native to Gemini Live's own VAD -- no hand-rolled interrupt
logic, but see the turn_detection="realtime_llm" note below (Phase 7):
LiveKit's own default "adaptive" interruption mode needs a local VAD
model this CPU can't run, so it's overridden explicitly. See
src/realtime/_compat.py for why the local_inference stub import below is
required on this machine in the first place.
"""

from . import _compat  # noqa: F401  -- must run before any livekit.agents import

import logging
import os

from dotenv import load_dotenv
from google.genai import types as genai_types
from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, JobContext
from livekit.plugins import google

from .orchestrator import run_interview, setup_interview

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("firstround.realtime")

# Pinned in Phase 0 -- see ARCHITECTURE.md. Deliberately not
# gemini-3.1-flash-live-preview (breaks multi-turn calls in this plugin).
LIVE_MODEL_ID = "gemini-2.5-flash-native-audio-preview-12-2025"

INSTRUCTIONS = (
    "You are FirstRound, an AI technical interviewer conducting a live "
    "voice interview for a Junior AI Engineer role at Northwind Labs. "
    "Speak naturally and concisely -- this is a spoken conversation, not "
    "text chat. You will be told exactly what to say by the interview "
    "orchestrator; say it close to word-for-word rather than improvising "
    "your own questions."
)


class InterviewerAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=INSTRUCTIONS,
            llm=google.realtime.RealtimeModel(
                model=LIVE_MODEL_ID,
                api_key=os.environ["GEMINI_API_KEY"],
                voice="Puck",
                # NOT setting context_window_compression: an empty
                # ContextWindowCompressionConfig() caused Gemini to reject
                # the session outright with a 1007 "invalid argument" close
                # on connect (malformed default, needs real sub-fields).
                # Not needed anyway -- audio-only session, so the default
                # 15-min cap already covers an 8+ min interview.
                #
                # Required for the orchestrator to receive
                # user_input_transcribed events (Phase 7) -- without this,
                # there's no text form of the candidate's spoken answer to
                # feed into the graph's Command(resume=...).
                input_audio_transcription=genai_types.AudioTranscriptionConfig(),
            ),
        )


server = AgentServer()


@server.rtc_session(agent_name="firstround-interviewer")
async def entrypoint(ctx: JobContext):
    # Do our own file I/O / graph-build / SQLite-checkpointer-open BEFORE
    # session.start() -- see orchestrator.py's module docstring for why
    # this ordering matters on this specific machine.
    interview_setup = await setup_interview()

    session = AgentSession(
        allow_interruptions=True,
        discard_audio_if_uninterruptible=True,
        # Explicit, not left to auto-select: LiveKit's own "adaptive"
        # interruption mode needs its local Silero VAD model
        # (livekit-local-inference), which SIGILLs on this CPU and is
        # stubbed out (see src/realtime/_compat.py). Barge-in worked fine
        # in local console mode but did not register at all over a real
        # room -- forcing realtime_llm here tells LiveKit to trust
        # Gemini Live's own native turn/interrupt signal instead of its
        # own (broken, on this machine) local VAD layer.
        turn_detection="realtime_llm",
    )
    try:
        await session.start(agent=InterviewerAgent(), room=ctx.room)

        # Wait for the candidate to actually be in the room before asking
        # anything. Without this the agent starts the interview the instant
        # it's dispatched -- which, if the room was created ahead of time
        # (as scripts/mint_lean_room.py does), means it asks its opening
        # question into an empty room and then hits the entrypoint timeout
        # ~5 minutes later, before the candidate ever clicks the join link.
        # Earlier tests only passed because the room already had a
        # participant sitting in it when the agent was dispatched.
        logger.info("waiting for candidate to join the room...")
        participant = await ctx.wait_for_participant()
        logger.info(f"candidate joined: {participant.identity} -- starting interview")

        await run_interview(session, interview_setup)
    finally:
        await interview_setup.close()


if __name__ == "__main__":
    agents.cli.run_app(server)
