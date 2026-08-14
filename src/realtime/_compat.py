"""Must be imported before anything else touches ``livekit.agents``.

This machine's CPU (Intel Celeron N4020 / Gemini Lake) has no AVX/AVX2/FMA.
``livekit-local-inference`` ships a native extension compiled assuming
those instructions, and simply importing it crashes the interpreter with
SIGILL (illegal instruction) -- not a Python exception, uncatchable.

``livekit.agents/__init__.py`` eagerly imports its ``inference`` subpackage,
which imports ``livekit.local_inference`` at module load time for its local
VAD and end-of-turn (EOT) detector models. We don't use either: the whole
point of the Gemini Live architecture (see ARCHITECTURE.md) is that Gemini
Live's own native VAD drives barge-in, not LiveKit's local inference stack.
So this stub replaces the module in ``sys.modules`` before the real one can
load, with objects that raise loudly if anything actually tries to use them.

Known limitation this creates: the PRD's documented fallback path (Groq
Whisper STT + LLM + TTS pipeline using LiveKit's local turn detector) is
NOT available on this hardware, since that fallback needs the exact stack
stubbed out here. If Gemini Live turns out unworkable, the fallback would
have to run on different hardware, not this laptop.
"""

import sys
import types

if "livekit.local_inference" not in sys.modules:
    _stub = types.ModuleType("livekit.local_inference")

    class _UnsupportedOnThisCPU:
        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "livekit-local-inference is stubbed out on this machine "
                "(CPU lacks AVX2, the native extension SIGILLs on import). "
                "This path should never be reached -- Gemini Live's native "
                "VAD is what actually drives barge-in here."
            )

    _stub.VAD = _UnsupportedOnThisCPU
    _stub.EOT = _UnsupportedOnThisCPU
    _stub.VAD_WINDOW_SAMPLES = 512  # matches the real package's constant
    _stub.init_vad = lambda *a, **k: None
    _stub.init_eot = lambda *a, **k: None

    sys.modules["livekit.local_inference"] = _stub


def _relax_gemini_websocket_keepalive() -> None:
    """Stop transient CPU starvation from killing the Gemini Live call.

    websockets defaults to ping_interval=20s / ping_timeout=20s. On this
    machine -- a 1.1GHz Celeron running the Python agent, Chrome doing
    WebRTC encode/decode, and a screen recorder, all at once -- the event
    loop can starve for longer than that, and the client then tears down
    a perfectly healthy connection: "sent 1011 keepalive ping timeout",
    followed by "1006 abnormal closure" and the interview dying mid-call
    (observed ~3.5 minutes into a real interview).

    google-genai hardcodes its ws_connect() call and exposes no way to
    pass ping settings through, so patch the binding directly. Pings are
    still SENT (so genuinely dead connections are still detected by the
    server side); only the client-side timeout that was firing on a
    false positive is disabled.
    """
    try:
        import google.genai.live as _genai_live
    except ImportError:  # google-genai not installed / not needed here
        return

    if getattr(_genai_live, "_firstround_keepalive_patched", False):
        return

    _original_ws_connect = _genai_live.ws_connect

    def _patched_ws_connect(*args, **kwargs):
        kwargs.setdefault("ping_interval", 20)
        kwargs.setdefault("ping_timeout", None)  # no client-side timeout
        return _original_ws_connect(*args, **kwargs)

    _genai_live.ws_connect = _patched_ws_connect
    _genai_live._firstround_keepalive_patched = True


_relax_gemini_websocket_keepalive()
