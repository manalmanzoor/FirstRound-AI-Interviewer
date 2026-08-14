# Submission

- **Timestamp:** 2026-08-14
- **JD chosen:** Junior AI Engineer — Northwind Labs, Karachi, 0–2 yrs
  (`inputs/jd.txt` — no real posting was available, so a realistic one
  was written to the PRD's specified role/level; disclosed rather than
  presented as a real posting)
- **Avatar used:** 2D canvas portrait, mouth driven by live amplitude
  analysis of the agent's real audio track (`web/join.html`; originally
  proven standalone in `web/avatar.html` against a real Gemini TTS clip)
- **Track:** 10-hour compressed track (PRD §6A) — all 12 core
  requirements, no bonus modules
- **Candidate for the real interview:** self. No partner was available in
  this window, so the builder is also the candidate. This is a disclosed
  constraint, not a hidden shortcut — the resume and GitHub profile
  driving the questions are genuinely mine (`inputs/resume.pdf`,
  github.com/manalmanzoor).
- **Consent line:** I, Manal Manzoor, am both the builder and the
  candidate in this recorded interview. I consent to this interview being
  recorded and to the recording, transcript, and resulting scorecard
  being used for grading and review of this assignment.

## Links

- **Repo:** this repository
- **Demo video:** _(to add)_
- **Code walkthrough video:** _(to add)_
- **Raw interview recording:** _(to add)_

## Measured latency

Measured on the dev machine (Intel Celeron N4020, no AVX2) — not
representative of normal hardware, but honest about what was observed.
Full detail in `ARCHITECTURE.md` → Measured Latency.

- Room connect (successful attempts): ~3–4s, logged client-side in
  `web/join.html` (`connect() resolved in Nms`)
- Real interview duration: ~11–12 min end to end (past the 8-min floor,
  under Gemini Live's 15-min audio-session cap)
- Barge-in: subjectively immediate, confirmed live by the candidate; not
  precisely instrumented (no interruption-latency timestamps added)

## Barge-in

Confirmed working in two separate settings:

1. **Console mode** (`python -m src.realtime.agent console`) during
   Phase 1 — the first proof, before the LiveKit room path worked.
2. **Over a real LiveKit room** during Phase 7 — confirmed live by the
   candidate mid-interview ("it's working and interrupting fine too").

Required a real fix to get there, not just configuration: LiveKit's
default `"adaptive"` interruption mode depends on a local Silero VAD
model that SIGILLs on this CPU (see `src/realtime/_compat.py`), so
barge-in registered *zero* effect over a real room while working fine in
console mode. Fixed by forcing `turn_detection="realtime_llm"` so LiveKit
defers to Gemini Live's own native turn/interrupt signal.

## What works

- Live voice interview driven end-to-end by the LangGraph state machine
  (7 nodes, 4 conditional edges, SQLite checkpointer with a real
  kill-and-resume proof)
- GitHub-grounded questions citing real repos/files/commits, verified
  programmatically rather than trusted (`question_planner.py`)
- Adaptive follow-up capped at 2 probes per competency, with live bluff
  detection feeding the final score
- Both guardrails, each proven by a test that actually fires it
  (`src/guardrails_test.py`)
- MCP server with all 5 required tools, verified live inside Claude
  Desktop
- HITL gate: approve / edit / reject all functionally distinct, using the
  same real pause-and-resume mechanism as the interview graph
- Evals: 5 personas ranked in exactly the expected order on the first
  real run, including the bluffer-below-nervous test that is the actual
  point of the exercise

## What's broken / known limitations

Full detail in `ARCHITECTURE.md` → Known Limitations. Summary:

- **LiveKit room-connect is intermittently broken on this machine** —
  an upstream `livekit/rust-sdks` FFI timeout this CPU loses under load.
  Using a custom minimal client instead of LiveKit Cloud's Console
  improved the hit rate but did not eliminate it; several interview
  attempts died before starting and needed a worker restart.
- **Speech-to-text sometimes transcribes English into Devanagari,
  Telugu or Malayalam script.** Setting the correct config field
  (`AudioTranscriptionConfig(language_codes=["en-US"])`, after first
  setting the wrong one) reduced but did not eliminate it. Garbled turns
  reach the scorer as garbage and depress the score.
- **The scorecard from the real interview under-represents the
  candidate.** The scorer picked the weakest fragments as evidence and
  returned a low score. The mechanism is correct — every evidence quote
  is independently re-verified against the real transcript — but the
  input it scored was degraded by the transcription issue above. Not
  tuned after the fact to look better, per PRD §1.
- **The scorer doesn't guarantee it scores every competency** in the
  question plan (found in Phase 6 evals; documented, not patched).
- **Deprecated LiveKit params** (`allow_interruptions`,
  `discard_audio_if_uninterruptible`) still in use instead of
  `turn_handling=TurnHandlingOptions(...)`.

## Bonus attempted

None — out of scope for the 10-hour track, as planned in PRD §6A.
