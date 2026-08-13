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
