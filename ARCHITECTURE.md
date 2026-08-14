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

## Phase 3 — LangGraph Assembly

### Graph

```
START -> intro -> resume_probe --stay--> resume_probe
                        |--next_node--> jd_fit --stay--> jd_fit
                                             |--next_node--> github_deepdive --stay--> github_deepdive
                                                                  |--next_node--> scenario --stay--> scenario
                                                                                       |--next_node--> candidate_qs -> wrap_up -> END
(any content node) --wrap_up--> wrap_up   [time_elapsed_s >= TIME_BUDGET_S, from any of the 4 content nodes]
```

7 nodes (intro, resume_probe, jd_fit, github_deepdive, scenario,
candidate_qs, wrap_up), 4 conditional edges (one per content node, each
its own `make_route_after_answer(source)` closure -- see below for why
it's 4 separate closures and not 1 shared function). Clears "6+ nodes,
2+ conditional edges" (requirement #5) with room to spare.

`scenario` has no dedicated question source in the schema (PRD section 4
only defines resume/jd/github) -- it's a catch-all for anything left
unasked, and in practice never fires once the other three sources are
each fully covered (confirmed in testing: 2 resume + 2 jd + 5 github = 9
of 9 planned questions, nothing left for scenario).

### State Object

`InterviewState` (src/graph.py) -- see the file for the full TypedDict.
Notable fields beyond the PRD's own skeleton: `last_evaluation` (the most
recent `AnswerEvaluation`, `None` when a node had nothing left to ask --
this doubles as the routing signal for "advance" vs "stay"),
`interview_start_ms` (real wall-clock, not a synthetic counter, since
this state needs to work identically whether test-driven or live), and
`github_grounded_questions_asked` (tracks requirement #4 directly in
state rather than recomputing it from the transcript later).

### Adaptive follow-up (requirement #6)

Backed by a lightweight per-turn evaluator (`src/agents/answer_evaluator.py`)
that classifies each answer as strong/shallow/bluff/off_topic/silence.
Shallow/bluff/off-topic/silence answers trigger a follow-up, capped at 2
per competency (`probe_count`); a strong answer or a hit probe cap moves
on. Per PRD section 11, this same evaluator is meant to back any future
live scoreboard too -- one pipeline, not two.

**Two real logic bugs found by actually inspecting test output, not just
checking for a clean exit code:**

1. Follow-up loop silently never fired. `is_follow_up` originally checked
   `current_id not in asked_question_ids` -- but a question's id gets added
   to `asked_question_ids` the moment it's *first* asked, before knowing
   whether a follow-up round is needed. So the very next loop-back already
   read that membership check as False, and the node asked a *new*
   question instead of following up. `probe_count` stayed empty even
   though routing was correctly deciding "follow up." Fixed by deriving
   `is_follow_up` purely from `last_evaluation` + `probe_count`, mirroring
   exactly the predicate the routing function itself uses, with no
   dependency on `asked_question_ids`.
2. Nodes advanced after their first question instead of cycling through
   all of a source's questions. The routing function didn't know which
   `source` its node was and couldn't tell "done with this question" from
   "done with every question of this type," so `github_deepdive` (5
   planned questions) moved on after asking just 1. Fixed by turning
   `route_after_answer` into `make_route_after_answer(source)`, a factory
   producing one closure per content node instead of one shared function
   -- each now checks whether more of *its own* source's questions remain
   before advancing.

Both were caught specifically because the test driver asserted on and
printed `probe_count` / `github_grounded_questions_asked`, not just
whether the graph ran to completion without crashing.

### Checkpointer resume (requirement #5)

`AsyncSqliteSaver`, proven with a real kill-and-resume test
(`src/graph_test.py`, Part 2): run a few turns, let the checkpointer/app
instance go out of scope entirely (no explicit close -- simulating a
crash), then build a *completely new* `StateGraph`/checkpointer/app
instance against the same SQLite file and thread_id. Confirmed the fresh
instance's `aget_state()` reports the correct next node (not START), and
that invoking it continues the interview correctly from there.

### Gemini free-tier quota, hit for real during this phase

`gemini-3.5-flash` (used through Phase 2) turned out to have only a
**20 requests/day** free-tier quota -- not just per-minute -- and it was
already exhausted partway through Phase 3's evaluator-heavy testing
(one evaluator call per candidate turn adds up fast). This is well below
the PRD's own estimate of "~15-30 calls total for the day." Switched
`OFFLINE_MODEL_ID` to `gemini-3.1-flash-lite`, which was still available
when 3.5-flash was fully exhausted -- implying a separate, larger quota
bucket, though the exact number isn't known (the public rate-limits page
requires the account owner's AI Studio login to see actual figures,
which wasn't available in this session). `src/agents/gemini.py` now
distinguishes per-minute 429s (worth a short wait-and-retry) from
per-day 429s (raises `DailyQuotaExhausted` immediately instead of
retrying -- waiting 60s against a daily cap is pointless), plus handles
transient 503 "model overloaded" errors with short exponential backoff.
**Open risk carried forward:** the rest of the day still needs many more
Gemini calls (scorer, guardrail tests, 5 eval personas, live-call
evaluation) -- worth checking actual remaining quota via AI Studio before
Phase 7.5's eval run, and having a second fallback model identified if
flash-lite also runs dry.

## Phase 4 — Avatar, HITL Gate, MCP Server

### MCP server (requirement #8)

`mcp_server/server.py`, the 5 required tools (`get_candidate`,
`get_question_plan`, `save_score`, `get_scorecard`, `list_interviews`).
Single-candidate/single-interview scope matches the actual project --
`interview_id`/`candidate_id` params exist for interface compliance with
the PRD's tool contracts, but resolve to the one canonical set of files
under `output/`, not a multi-tenant store.

**PRD's documented import (`from mcp.server.fastmcp import FastMCP`) is
stale.** The `mcp` PyPI package (2.0.0, current as of this build) no
longer ships a `fastmcp` submodule at all -- its internal structure has
been reorganized (`mcpserver`, `lowlevel`, `apps`, etc., no `fastmcp`).
The high-level `FastMCP` convenience API the PRD's "FastMCP 3.x" comment
actually refers to now lives in the separate standalone `fastmcp` PyPI
package (confirmed: installed version is literally `3.4.7`). Fixed by
installing `fastmcp` directly and importing `from fastmcp import FastMCP`
instead. Also note for this version: `@mcp.tool()`-decorated functions
are callable directly as plain functions in tests (no `.fn` unwrapping
needed, unlike some other MCP SDK versions).

**Claude Desktop config location is also non-standard on this machine.**
The documented path (`%APPDATA%\Claude\claude_desktop_config.json`)
doesn't exist here -- this machine's Claude app is installed as an
MSIX-packaged Windows app, with its config virtualized to
`AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json`.
Added an `mcpServers` key there pointing at the venv's `python.exe` +
`mcp_server/server.py`, preserving all existing app preferences. Verified
working live in Claude Desktop: shows up as a connected "firstround"
tool with 5 tools, and a real `list_interviews` call round-tripped
correctly through the actual app (not just unit-tested in isolation).

### HITL gate (requirement #7)

`src/hitl.py` -- deliberately reuses the same `interrupt()`/
`AsyncSqliteSaver` checkpointer pattern proven in Phase 3's interview
graph, rather than a plain CLI prompt bolted on the side. This is what
makes the pause "genuine" per the requirement: it's a real graph
suspension a fresh process can resume, not just a blocking `input()`
call with no persistence. All three actions (approve/edit/reject) proven
functionally distinct via `src/hitl_test.py`: approve sets
`approved_by_human=True` with no changes; edit rewrites specific question
text by id and logs exactly what changed; reject sets
`approved_by_human=False` and records a reason. `src/hitl.py`'s own
`run_interactive()` is the real human-facing CLI (not yet a polished UI
screen -- per PRD section 11, UI polish is explicitly deferred to Phase
9, and what's graded here is that the pause and all three actions
actually work, which they do).

### 2D Avatar (requirement #1, partial)

Built as **pure frontend, standalone from LiveKit** (`web/avatar.html`):
a canvas-rendered face whose mouth openness is driven live by Web Audio
API amplitude analysis (`AnalyserNode.getByteFrequencyData`) of whatever
audio is playing, smoothed frame-to-frame to avoid jitter. This
deliberately decouples avatar development from the still-unresolved
LiveKit room-connect bug (Phase 1) -- the lip-sync technique itself
needs no LiveKit room at all to prove out, only *any* audio source, the
same way console mode let Gemini Live's barge-in get proven without a
real room.

Tested against **real Gemini TTS audio**, not a synthetic tone --
`scripts/generate_tts_sample.py` generates a real clip via
`gemini-2.5-flash-preview-tts` (`web/sample_tts.wav`). Confirmed working
by manually loading it in a browser and watching the mouth track the
speech.

**What's still open:** this is the avatar *technique* proven in
isolation, not yet wired into the real LiveKit call. The intended full
picture (per PRD section 2's "pure frontend" framing): the candidate's
browser (the join page, not yet built) receives the agent's audio track
over LiveKit like any other participant, and runs this exact same
amplitude-analysis technique locally against that live track -- no video
track needs to be published by the Python agent worker at all, which
also means the avatar doesn't depend on solving the room-connect bug's
*root cause*, only on the room connecting at all. Wiring this into a
real join page is deferred alongside the room-connect fix (see Phase 1
Open/Unresolved) since real end-to-end testing needs a working room
either way.

## Phase 5 — Scorecard & Guardrails

### Guardrails (requirement #9)

Both live in `src/guardrails/`, both proven by `src/guardrails_test.py`
(9 banned-topic categories, 4 legitimate-question false-positive checks,
5 evidence-check cases) -- not just a code comment claiming they work.

- `banned_questions.py` (#9a): keyword/regex blocklist across the 8 PRD
  categories (age, gender, marital status, religion, nationality,
  health/pregnancy, salary history, politics), checked in
  `src/nodes/_content_node.py` *before* a question is ever selected to
  ask -- both for fresh questions pulled from the plan and for generated
  follow-up trigger text (which falls back to a fixed, pre-reviewed
  generic follow-up if a trigger somehow touches a banned topic). Chose
  regex over an LLM classifier deliberately: a "blocklist" should be
  deterministic and near-zero latency on every single question, and a
  test "proving it fires" is far more reliable against a deterministic
  check than a stochastic model call. First-draft patterns missed several
  real phrasings during testing ("planning to have children" vs the
  original `plans? to`, "are you currently pregnant" vs the original
  `are you pregnant`, "salary at your last job" vs pattern names anchored
  to the wrong phrase) -- broadened based on what the test suite actually
  caught, not guessed in advance.
- `evidence_check.py` (#9b): stronger than "field is non-empty" --
  rejects unless `evidence_quote` is a real, verbatim substring of one of
  the *candidate's* transcript turns (normalized for whitespace/case). A
  fabricated-but-plausible quote, or a quote sourced from the agent's own
  turn, is rejected just as an empty one is. The same function backs both
  `mcp_server/server.py`'s `save_score` (rejects the write) and
  `src/agents/scorer.py` (flags any competency whose LLM-generated
  evidence doesn't check out) -- one guardrail implementation enforced in
  two places, not two independently-drifting copies.

**Bugs caught while wiring guardrails into the graph, not just in the
guardrail modules themselves:** the `guardrail_flags` list in
`_content_node.py` had two separate `state["guardrail_flags"] + [...]`
assignments (one for skipped banned-topic questions, one for bluff
detection) that would silently overwrite each other if both fired in the
same turn, since both started from the same pre-update `state` rather
than accumulating. Also, questions skipped for a banned topic weren't
being added to `asked_question_ids`, which would have made
`_next_question` re-skip (and re-flag) the same question indefinitely.
Both fixed before considering this done.

### Scorecard (requirement #10)

`src/agents/scorer.py`: `transcript.json` + `question_plan.json` ->
`scorecard.json`, matching the PRD section 4 schema exactly. The prompt's
single most important instruction, stated first and explicitly (PRD
section 1): a confident-sounding but wrong or hand-wavy answer must score
*below* a hesitant-but-correct one -- fluency is explicitly not the
signal, substance is. Every `guardrail_flags` entry gathered live during
the interview (bluff detections) is passed into the scoring prompt as a
hint to pull that competency's score down, not silently dropped. Real
discriminative validation of this (bluffer scoring below nervous-correct)
is Phase 6's job with purpose-built personas -- what's proven here is
that the mechanics work end-to-end: tested against a real transcript
(`src/graph_test.py`'s scripted run), produced a schema-valid scorecard
with every `evidence_quote` independently re-verified against the real
transcript via the same `evidence_check` guardrail
(`src/agents/guardrails_bridge.py`), and correctly gave a low score with
specific, evidence-referenced reasoning (not generic platitudes) once the
scripted answers degraded into repeated filler text -- not fooled by the
earlier, more fluent-sounding turns.

**`guardrail_flags`/`github_grounded_questions_asked`/`duration_seconds`
live in graph state, not in the PRD's fixed `transcript.json` schema
(which is just `{"turns": [...]}`)** -- without carrying them over
somewhere, the scorer would never see the bluff flags gathered live
during the interview. PRD section 4 explicitly allows extra fields ("do
not deviate -- extra fields OK, missing fields are not"), so
`src/nodes/wrap_up.py` adds them as extra top-level fields on
`transcript.json` rather than inventing a second output file.

**Small bug caught by reading the actual output, not just checking the
schema validated:** the model has no reliable notion of "today" and
invented a plausible-but-wrong `interview_date` on the first real run.
Fixed by setting it programmatically after the structured call, the same
way `duration_seconds`/`guardrail_flags`/`github_grounded_questions_asked`
already were.

## Phase 6 — Evals (requirement #11)

`evals/personas/generate_personas.py` builds 5 synthetic
transcript.json-shaped files (Strong/Nervous/Average/Bluffer/Weak), all
answering the exact same real 9-question plan
(`output/prep/question_plan.json`, produced from the real resume +
GitHub data in Phase 2) so the comparison is apples-to-apples rather than
5 different question sets. `evals/run_evals.py` runs every persona
through the actual `src/agents/scorer.py` -- the same scorer a real
interview uses, not a mock or a simplified eval-only path -- and writes
the ranking table plus honest notes to `evals/results.md`.

**Result: exact expected ranking on the first real run**
(`strong 4.30 > nervous 3.00 > average 2.00 > bluffer 1.00 = weak 1.00`),
including the specific test PRD section 1 calls out as the real one:
bluffer scored below nervous despite Bluffer's answers being written to
read more fluent and confident than Nervous's. This wasn't tuned to get
there -- the persona answer text was written once, before ever running
the scorer, specifically so a clean result couldn't be the product of
iterating against the output.

That said, two things in the raw output are reported honestly rather
than smoothed over in `results.md` (PRD section 1: "a suspiciously
perfect eval table reads as fabricated"):
- Bluffer and Weak tied at exactly 1.00 -- the core test held, but these
  are meant to be distinguishable failure modes (actively misleading vs.
  honestly out of their depth), and a 1-5 scale with every competency
  floored at 1 has no room left to separate them.
- Bluffer's scorecard is missing a `communication` competency entry that
  every other persona has, despite every persona answering the same
  communication-tagged question (q9) -- the model silently omitted
  scoring that competency rather than scoring it low. The scorer's
  evidence_quote is validated downstream (`guardrails_bridge.py`);
  competency-set completeness currently isn't, and probably should be.

## Measured Latency (filled in as each piece comes online)

## Known Limitations (filled in honestly as they're found — see PRD §1)

- LiveKit WebRTC room connection does not currently work on the dev
  machine (see Phase 1 above) — reproducible upstream bug, not yet solved.
- LiveKit's local-inference VAD/turn-detector/EOT stack is unusable on
  this CPU (SIGILL), so the PRD's own documented Gemini-Live fallback path
  (Groq Whisper + LiveKit local turn detection) is not available here.
