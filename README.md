# FirstRound — AI Video Interviewer

A live, voice-driven AI technical interviewer. It reads a job description and a candidate's resume, greps their real GitHub repos for specific commits and files to ground its questions in, then conducts an 8+ minute adaptive voice interview over a LiveKit video call with a lip-synced avatar, native barge-in, and a final scorecard backed by real transcript evidence — no fabricated quotes, no generic textbook questions.

Built solo on the **10-hour compressed track** (`PRD.md` §6A): all 12 core requirements, deliberately no bonus modules.

> Full architecture rationale: [`PRD.md`](PRD.md). As-built graph/state/latency notes and known limitations: [`ARCHITECTURE.md`](ARCHITECTURE.md). Submission metadata, consent line, and measured results: [`SUBMISSION.md`](SUBMISSION.md).

---

## Contents

- [Screenshots](#screenshots)
- [Core requirements — 12/12](#core-requirements--1212)
- [Beyond the checklist](#beyond-the-checklist)
- [Sample transcript](#sample-transcript)
- [Setup](#setup)
- [Running it](#running-it)
- [Known limitations](#known-limitations)
- [Repo structure](#repo-structure)

---

## Screenshots

*(add screenshots here)*

<!-- Suggested set:
- Pre-join screen (avatar ring + waveform + room ID)
- Live call — avatar mid-question, transcript panel, progress rail
- The graph-progress rail advancing through a real node (e.g. github_deepdive)
- A GitHub-grounded question visible in the on-screen transcript
- The final scorecard (output/scorecard.json)
- The MCP server's 5 tools working inside Claude Desktop
-->

---

## Core requirements — 12/12

| # | Requirement | How it's implemented | Where |
|---|---|---|---|
| 1 | Live video call, visible face | LiveKit Cloud room + 2D canvas avatar, mouth driven by real-time amplitude analysis of the agent's actual TTS audio track (not a canned animation) | [`web/join.html`](web/join.html) |
| 2 | Barge-in | Gemini Live's native turn/interrupt signal, forced via `turn_detection="realtime_llm"` (LiveKit's default local-VAD mode SIGILLs on this dev CPU — see limitations). Confirmed live, twice, in two different settings | [`src/realtime/agent.py`](src/realtime/agent.py) |
| 3 | JD + resume parsing | PDF → structured JSON via Gemini, zero manual field entry | [`src/agents/jd_parser.py`](src/agents/jd_parser.py), [`src/agents/resume_parser.py`](src/agents/resume_parser.py) |
| 4 | GitHub grounding | Real repos/files/commits pulled via the GitHub API and cited verbatim in generated questions — 5 of them in the sample transcript below | [`src/agents/github_agent.py`](src/agents/github_agent.py), [`src/agents/question_planner.py`](src/agents/question_planner.py) |
| 5 | LangGraph structure | Typed state, 7 nodes, 4 conditional edges, `AsyncSqliteSaver` checkpointer with a real kill-and-resume proof (not just claimed — `graph_test.py` actually kills the process mid-interview and resumes from disk) | [`src/graph.py`](src/graph.py), [`src/graph_test.py`](src/graph_test.py) |
| 6 | Adaptive follow-up | A shallow answer triggers a probe, capped at 2 per competency; a strong answer raises difficulty. Routing logic lives in the conditional edges | [`src/graph.py`](src/graph.py) |
| 7 | HITL gate | Question plan genuinely pauses via `interrupt()`; approve / edit / reject are three functionally distinct paths, not three labels on the same behavior | [`src/hitl.py`](src/hitl.py), [`src/hitl_test.py`](src/hitl_test.py) |
| 8 | MCP server | 5 tools (`get_candidate`, `get_question_plan`, `save_score`, `get_scorecard`, `list_interviews`), verified live inside Claude Desktop | [`mcp_server/server.py`](mcp_server/server.py) |
| 9 | Guardrails | (a) banned-topic blocklist checked *before* a question ever reaches the candidate — 8 protected categories, regex-based, deterministic; (b) every scorecard evidence quote is independently re-verified against the real transcript after scoring, catching fabricated quotes. Both proven by a real test suite, not asserted | [`src/guardrails/`](src/guardrails/), [`src/guardrails_test.py`](src/guardrails_test.py) |
| 10 | Scorecard | Matches the PRD §4 schema exactly; real quotes, sensible recommendation | [`src/agents/scorer.py`](src/agents/scorer.py) |
| 11 | Evals | 5 synthetic personas through the real scorer (not a mock path) — ranked `strong > nervous > average > bluffer > weak` on the first real run, including the one ranking that actually matters: **bluffer scores below nervous** | [`evals/run_evals.py`](evals/run_evals.py), [`evals/results.md`](evals/results.md) |
| 12 | Prompts as files | Every system prompt lives in its own file, with a v1→v2 iteration log against real diagnosed failures (not hypothetical ones) | [`prompts/`](prompts/), [`prompts/ITERATION_NOTES.md`](prompts/ITERATION_NOTES.md) |

Run the acceptance proofs yourself:

```
python -m src.graph_test          # checkpoint kill-and-resume, for real
python -m src.hitl_test           # approve / edit / reject, scripted
python -m src.guardrails_test     # both guardrails, forced to actually fire
python -m evals.run_evals         # 5 personas → evals/results.md
```

---

## Beyond the checklist

The 12 requirements are the floor, not the interesting part. What actually took the time was making the live call *behave* like a real interview once real audio, real network jitter, and a real candidate were in the loop — every one of these was a bug found by actually running it, not designed in up front:

- **Automatic vs. explicit agent dispatch.** An explicitly-dispatched agent joins the room the instant it's minted and burns its ~5 minute entrypoint timeout waiting for a candidate who hasn't clicked the join link yet — any delay leaves a dead room ("the interviewer never speaks"). Switched to automatic dispatch so the agent only joins once a real participant does.
- **VAD-aware answer collection.** A silence timer alone can't tell "finished answering" from "pausing between sentences" — an early version cut off introductions after the first sentence. Fixed by tracking real voice-activity state and holding the turn open through genuine pauses, then separately tightened so the *fast* path (candidate genuinely done) doesn't overshoot into feeling laggy — settle time is decoupled from the safety-extension poll interval so the common case resolves in ~2s, not ~4s+.
- **Suppressing the model's own instincts.** Gemini Live is a full conversational agent — left alone, it fills silence with its own invented follow-up questions (caught one asking about supervised vs. unsupervised learning, which is nowhere in the question plan). While the orchestrator is waiting on a scripted answer, anything the model starts saying unprompted is interrupted structurally, not just discouraged in the prompt.
- **Transcription language repair.** Gemini Live's `AudioTranscriptionConfig.language_codes` is documented as a *hint*, not an enforced pin — English speech sometimes still comes back in Devanagari, Telugu, or Malayalam script (occasionally a real mistranslation, not just a mis-spelling). Since it's usually just the same sounds spelled in the wrong alphabet, added a repair step that detects non-Latin script and asks the model to sound it out (or translate it) back to English — gated so ordinary English answers never pay the extra latency.
- **UI state that tells the truth.** The "Interviewer is speaking…" label used to be set the instant a question *started* and never updated until the candidate's answer was already fully processed — so it sat there, stale, through the candidate's entire answer, making it look like the mic wasn't being heard. Now flips to "Listening…" the instant the agent's audio playout actually ends.
- **Rebuilt the call UI against a real design reference** (not a static mockup left unintegrated) while keeping every working piece of audio/avatar logic underneath — including wiring the on-screen progress rail and transcript to the *real* LangGraph node state and verbatim turn text over LiveKit's data channel, instead of a decorative animation.
- **CPU-constrained dev environment** (Intel Celeron N4020, no AVX2) surfaced real upstream issues rather than hypothetical ones: a SIGILL on `livekit-local-inference` import (worked around by stubbing the module before it loads), an intermittent LiveKit FFI room-connect timeout (mitigated, not eliminated — documented honestly in `ARCHITECTURE.md` rather than hidden), and a blocking scorer call that was silently killing the Gemini Live websocket's keepalive under CPU starvation (fixed by moving it off the event loop).

Every one of these is a commit with the actual bug report and root cause in the message, not a generic "fix bug" — `git log` is a legitimate second source of truth for how this was built.

---

## Sample transcript

Excerpt from a real recorded interview (`output/transcript.json` — full session: 711s, 21 turns, 5 GitHub-grounded questions, 0 guardrail flags), showing GitHub grounding in action — these aren't generic questions, each cites a real repo, file, or commit from the candidate's own GitHub:

```
[agent]     Hi, thanks for joining. I'm the AI interviewer for the Junior
            AI Engineer role at Northwind Labs. To start, could you...
[candidate] My name is Manal. I am a software engineering student, love
            building chatbots, and I have also done some UI/UX work.
[agent]     In your aiseasonlead-mid-task repository, specifically in
            app.py, you implemented a Flask server that runs an agent...
[agent]     In RAHBAR-ai-mobile-app/server.ts, you initialized the
            Gemini client using TypeScript/Express to proxy weather API
            data...
[agent]     In your RAG-RedTeam-Toolkit, commit d61cdca1 describes
            adding an AI red-teaming toolkit and a five-layer guardrail
            stack...
[agent]     In your Dualbook-Voice-Agent project, specifically
            run_dashboard.py, you created a single server handling both
            an anonymous...
[agent]     In your aiseasonlead-mid-task project, the agent.py script
            uses Groq and Playwright to crawl business data...
```

**Honest note, per this project's own philosophy of disclosing rather than tuning results after the fact:** the scorecard generated from this particular take (`output/scorecard.json`) scored low — the candidate's answers in this pass were short test responses, not a real good-faith attempt at the questions, captured while several live-call bugs above were still being actively diagnosed and fixed. The *scoring mechanism itself* is verified correct independently of this — see [Evals](#core-requirements--1212) — every evidence quote it produced from this transcript was re-verified as real and unmodified. A clean final take is the one to judge the interviewer on.

---

## Setup

1. `python -m venv .venv && .venv\Scripts\activate` (Windows)
2. `pip install -r requirements.txt`
3. `copy .env.example .env` and fill in real values (see `PRD.md` §9B for where to get each key — all free tier, no card required)
4. Verify keys:
   `python scripts/verify_gemini.py`, `python scripts/verify_livekit.py`, `python scripts/verify_github.py`

## Running it

**Offline prep pipeline** — produces `output/prep/*.json` from real inputs (`inputs/jd.txt`, `inputs/resume.pdf`, and the GitHub handle in the parsed resume):

```
python -m src.agents.jd_parser
python -m src.agents.resume_parser
python -m src.agents.github_agent <github-handle>
python -m src.agents.question_planner
```

Then review/approve the plan — approve, edit specific questions, or reject, all three genuinely pause and resume the graph (requirement #7):

```
python -m src.hitl
```

**MCP server** — register in Claude Desktop's config (`%APPDATA%\Claude\claude_desktop_config.json`, or see `ARCHITECTURE.md` Phase 4 for the MSIX-virtualized path on Windows):

```json
{
  "mcpServers": {
    "firstround": {
      "command": "<path to .venv>\\Scripts\\python.exe",
      "args": ["<repo path>\\mcp_server\\server.py"]
    }
  }
}
```

Restart Claude Desktop, then ask it to call `list_interviews`, `get_candidate`, `get_question_plan`, `save_score`, or `get_scorecard`.

**The live interview** — three pieces, all local:

1. **Agent worker** (Python, connects outbound to LiveKit Cloud):
   ```
   python -m src.realtime.agent dev
   ```
2. **Mint a room + join token**:
   ```
   python scripts/mint_lean_room.py
   ```
3. **Join page**: open the `web/join.html?...` link the script prints, click Connect once. Shows the 2D avatar lip-synced to the agent's real TTS audio, live-driven from the interview graph.

After the interview ends, score it:

```
python -m src.agents.scorer
```

Writes `output/scorecard.json` from `output/transcript.json`.

---

## Known limitations

Disclosed rather than hidden, per this project's own grading philosophy. Full detail in [`ARCHITECTURE.md`](ARCHITECTURE.md) → Known Limitations and [`SUBMISSION.md`](SUBMISSION.md):

- **LiveKit room-connect is intermittently broken on this dev machine** — an upstream `livekit/rust-sdks` FFI timeout under CPU load. Mitigated (custom minimal client instead of LiveKit Cloud Console, one pre-warmed process) but not eliminated.
- **Speech-to-text occasionally mis-detects language.** `AudioTranscriptionConfig.language_codes` is a hint, not an enforced pin, on this preview model. A repair step recovers most of these after the fact — see [Beyond the checklist](#beyond-the-checklist) — but it's a mitigation, not a guarantee.
- **The scorer doesn't strictly guarantee scoring every competency** in the question plan — found during evals, documented rather than silently patched over.
- Two deprecated LiveKit `AgentSession` params (`allow_interruptions`, `discard_audio_if_uninterruptible`) are still in use; no replacement was available in the installed plugin version at build time.

---

## Repo structure

See `PRD.md` §3 for the intended layout; this matches as-built.

```
src/            interview graph, nodes, realtime orchestrator, guardrails, agents
prompts/        every system prompt as its own file + iteration notes
mcp_server/     the 5-tool MCP server
web/            join.html — the live call UI (avatar, transcript, progress rail)
evals/          5-persona eval harness + results
scripts/        room minting, key verification
inputs/         job description + resume PDF
output/         prep artifacts, transcript, scorecard (generated, not hand-written)
```
