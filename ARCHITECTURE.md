# Architecture

Living doc — updated at the end of each build phase with what actually
happened, not what was planned. See `PRD.md` for the full design rationale.

## Phase 0 — Keys & Scaffolding

**Gemini Live model ID decision:** pinned to `gemini-2.5-flash-native-audio-preview-12-2025`,
not the newer `gemini-3.1-flash-live-preview`. Reason: LiveKit's Python agents
Gemini plugin has a known, currently-open bug where 3.1 rejects
`send_client_content` with a 1007 error after the first model turn, and
`generate_reply()` / `update_instructions()` / `update_chat_ctx()` are
incompatible with 3.1 models. An interview is inherently multi-turn, so 3.1
is unusable here today regardless of how "current" it looks. Re-check this
before demo day in case the plugin has patched it.

**Session duration finding:** without `contextWindowCompression` enabled,
Gemini Live audio-only sessions cap at 15 minutes and audio+video sessions
cap at 2 minutes. The interview only needs to send the candidate's
**microphone audio** into Gemini Live — the avatar video is rendered
client-side off the TTS/audio stream, not sent to the model — so this should
land in the audio-only 15-minute bucket, comfortably covering the 8+ minute
requirement. Flagging as a Phase 1 acceptance check: confirm no video track
is being fed into the Live API session, and enable
`contextWindowCompression` anyway as a safety margin. WebSocket connections
also terminate around 10 minutes regardless — `SessionResumptionConfig`
(tokens valid 2h) is the mechanism to reconnect without losing context if
the interview runs long.

**Offline reasoning model:** `gemini-2.5-flash` and `gemini-2.5-flash-lite`
are both dead for this (newly created) account — `generate_content` returns
404 "no longer available to new users," even though `models.list()` still
lists them as present. The list endpoint is not a reliable existence check;
only an actual call proves access. Confirmed working replacement:
`gemini-3.5-flash` (offline reasoning), with `gemini-3.1-flash-lite` as the
same-provider fallback if RPM gets tight — same free-tier deal, newer
generation. This is exactly the "don't trust a remembered/hardcoded model
name" risk the PRD called out for the Live model, and it turned out to
apply to the offline model too.

## Phase 1 — Joinable Call & Barge-In

**This machine's CPU (Intel Celeron N4020, no AVX/AVX2/FMA) breaks LiveKit's
native extensions in two separate ways.** Both had to be worked around
before anything else in Phase 1 could run:

1. `livekit-local-inference` (bundled local VAD/end-of-turn models) SIGILLs
   the interpreter on `import` — not a Python exception, uncatchable, kills
   the whole process. `livekit.agents/__init__.py` eagerly imports it. Fixed
   by pre-populating `sys.modules['livekit.local_inference']` with a stub
   before any `livekit.agents` import (see `src/realtime/_compat.py`). We
   don't lose anything functionally: the architecture already uses Gemini
   Live's own native VAD for barge-in, never LiveKit's local inference
   stack. **Known limitation this creates:** the PRD's documented fallback
   path (Groq Whisper STT + LLM + TTS pipeline using LiveKit's local turn
   detector) needs the exact stack stubbed out here, so it is NOT available
   on this hardware if Gemini Live turns out unworkable later.

2. `Agent(llm=RealtimeModel(context_window_compression=ContextWindowCompressionConfig()))`
   with an empty/default config causes Gemini to reject the session
   outright: `1007 Request contains an invalid argument` on the very first
   connect. Not investigated further under time pressure — dropped
   entirely, since the interview only sends candidate mic audio (not
   video) into the Live session, so the default 15-minute audio-only cap
   already comfortably covers an 8+ minute interview without it.

**Barge-in fix:** initial testing showed the agent finishing its current
sentence before responding to an interruption, instead of cutting off
instantly — a real requirement-#2 failure, not a formatting nitpick.
Gemini's native VAD was correctly detecting the interruption and stopping
*new* generation, but audio already generated and queued on LiveKit's
output track kept playing out from that buffer. Fixed with
`AgentSession(discard_audio_if_uninterruptible=True)`, which flushes the
output buffer immediately on interruption. Confirmed working via
`python -m src.realtime.agent console` (local mic/speaker loopback,
bypasses the LiveKit WebRTC room entirely) — see SUBMISSION.md for the
timestamped proof.

**Open, unresolved: LiveKit room connect (WebRTC) fails ~100% of the time
on this machine.** Every attempt to join a real LiveKit room (tested via
the LiveKit Cloud Console, 4/4 attempts) crashes the worker process with:

```
livekit_ffi::server::room - timed out waiting for ReadyForRoomEventRequest after ConnectCallback
```

This is a confirmed **open upstream bug** in `livekit/rust-sdks`
([issue #1188](https://github.com/livekit/rust-sdks/issues/1188),
[PR #1261](https://github.com/livekit/rust-sdks/pull/1261), still
unmerged) — the PR description states plainly: *"slow Python applications
could still exceed the timeout"* waiting to send `ReadyForRoomEventRequest`
after connect. We are on `livekit==1.1.14`, already the latest release; no
newer package fixes this. Ruled out as *not* the cause: Windows Defender
real-time scanning (added a project exclusion, no change), Chrome/VS Code
CPU contention (closed both, no change — though CPU load reads ~100% on
this box more or less constantly), a VPN or system proxy (none present),
a blanket UDP block (raw STUN test to a public server succeeded in 0.24s),
and the Windows `ProactorEventLoop` (forced `WindowsSelectorEventLoopPolicy`
instead — confirmed active via the "Using selector: SelectSelector" log
line — identical crash, same failure point, ~27s in that run vs. ~19s in
earlier runs). The remaining, most likely explanation given the upstream
PR's own wording: this specific low-power CPU (quad-core, 1.1GHz, no
AVX2) is consistently too slow to win the race against a timeout that
isn't currently configurable from the Python API surface.

**Practical consequence:** Gemini Live + native barge-in are proven to
work end-to-end (via `console` mode, no real room). The actual LiveKit
room / WebRTC video call — needed for core requirement #1 (visible face,
raw recording) and to test barge-in over a real network path rather than
local loopback — is still blocked. Deferred rather than solved: revisit
before Phase 8 (the real interview), where the options are (a) keep
digging for a workaround/config override, (b) run the agent worker on
different hardware for just the recorded interview, or (c) wait and see
if `rust-sdks` merges a fix. Flagged to the user as a serious, real risk
to the "8+ min continuous video call" requirement, not glossed over.

Minor, unrelated note picked up along the way: `AgentSession(allow_interruptions=..., discard_audio_if_uninterruptible=...)` are both deprecated in this livekit-agents version, replaced by `turn_handling=TurnHandlingOptions(...)`. Left as-is for now since it still works and v2.0 isn't out yet — worth migrating if there's spare time later.

## Phase 2 — Prep Graph (offline)

Pipeline: `jd_parser` → `resume_parser` → `github_agent` → `question_planner`
(gap analysis folded directly into `question_planner`'s prompt rather than
a separate file/schema, matching the PRD's repo structure which doesn't
name a standalone `gap_analysis.py`). All four steps ran cleanly against
real inputs: a drafted JD (`inputs/jd.txt`, no real posting was available
so a realistic one was written matching the PRD's role/level), the
candidate's real resume PDF (`inputs/resume.pdf`), and their real GitHub
profile (`manalmanzoor`).

Result: 9 questions total -- 5 GitHub-sourced (requirement #4 needs >=3),
2 resume-sourced, 2 JD-gap-sourced. Every GitHub question cites a real
fetched repo/file/commit (`_validate_github_grounding` in
`question_planner.py` checks this programmatically, not just by eyeballing
the prompt) -- e.g. a specific function name in a real file
(`aiseasonlead-mid-task/app.py`'s `_prune_jobs`), a real commit SHA
(`RAG-RedTeam-Toolkit commit d61cdca1`). Genuinely specific, not generic
"tell me about this repo" filler.

**Model note:** offline reasoning uses `gemini-3.5-flash` via structured
output (`response_schema=<PydanticModel>`), the model confirmed working in
Phase 0. Same model handles JD parsing, resume parsing, and question
planning -- no separate model needed per step.

**Transient issue, not a real bug:** `github_agent.py` hit an
`SSLEOFError` on one commit-history request mid-run (unexpected EOF during
TLS handshake) -- a one-off network blip, not reproducible, but since the
pipeline makes many sequential GitHub API calls a single flaky connection
shouldn't kill the whole prep run. Added a small retry-with-backoff
wrapper around `_get()` (3 attempts, 1.5s/attempt backoff) rather than
letting it be fatal.

## Graph (filled in during Phase 3.5–5)

## State Object (filled in during Phase 3.5–5)

## Measured Latency (filled in as each piece comes online)

## Known Limitations (filled in honestly as they're found — see PRD §1)

- LiveKit WebRTC room connection does not currently work on the dev
  machine (see Phase 1 above) — reproducible upstream bug, not yet solved.
- LiveKit's local-inference VAD/turn-detector/EOT stack is unusable on
  this CPU (SIGILL), so the PRD's own documented Gemini-Live fallback path
  (Groq Whisper + LiveKit local turn detection) is not available here.
