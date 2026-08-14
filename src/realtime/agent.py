"""Phase 1: joinable LiveKit call with a Gemini Live voice agent.

Barge-in is native to Gemini Live's own VAD (enabled by default) -- no
hand-rolled interrupt logic. See src/realtime/_compat.py for why the
local_inference stub import below is required on this machine.
"""

from . import _compat  # noqa: F401  -- must run before any livekit.agents import

import logging
import os

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, JobContext
from livekit.plugins import google

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
    "text chat. Ask one question at a time and wait for the candidate's "
    "full answer before responding."
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
                # 15-min cap already covers an 8+ min interview. Revisit if
                # a proper sliding-window config is needed later.
            ),
        )


server = AgentServer()


@server.rtc_session(agent_name="firstround-interviewer")
async def entrypoint(ctx: JobContext):
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
    await session.start(agent=InterviewerAgent(), room=ctx.room)
    await session.generate_reply(
        instructions="Greet the candidate warmly in one sentence and ask them to introduce themselves."
    )


if __name__ == "__main__":
    agents.cli.run_app(server)
