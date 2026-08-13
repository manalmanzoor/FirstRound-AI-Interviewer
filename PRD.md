# FirstRound — AI Video Interviewer
### Product & Build Requirements Document
**JD selected:** Junior AI Engineer — Northwind Labs, Karachi, 0–2 yrs
**Avatar strategy:** 2D lip-synced avatar only (no paid vendor key, no trial-credit risk)
**Dev environment:** Claude Code, local machine
**Grading:** 100 core + 20 bonus, viva is a pass/fail gate (fail caps total at 40)

---

## 1. What Actually Gets Graded

Before touching code, internalize this because it should drive every close call during the 24 hours:

- The **evidence-quote requirement** on the scorecard isn't a formatting rule — it's the actual product. A score with no quote is rejected by your own guardrail, not just the grader.
- The real test is **persona #4 vs #5**: a confident bluffer must score *below* a nervous-but-correct candidate. Anyone can separate Strong from Weak. This is what makes it an evaluation system instead of a chatbot.
- **Honest limitations score points in three separate places** (evals, prompt iteration notes, ARCHITECTURE.md). Do not polish these away to look impressive — a suspiciously perfect eval table reads as fabricated.
- The viva assumes an AI could have written all of this. Nothing goes into the repo that you can't explain and modify live, on camera, half-asleep.
- Grader's one real question for the demo: *"Would a real candidate believe they were being interviewed?"* Optimize for that over any single rubric line item.

---

## 2. Architecture Decisions (and why, vs. the doc's defaults)

| Layer | Decision | Reasoning |
|---|---|---|
| **Realtime voice brain** | Gemini Live API | Native barge-in built in — satisfies requirement #2 without hand-rolled VAD/interrupt logic. **Known risk:** there's an active, unresolved bug where the model can cut itself off mid-sentence, and specific native-audio model versions have been deprecated recently. Pull the current live model ID from AI Studio at build time — don't trust a hardcoded name from any tutorial. This is why it's hour 1–3 in the plan: highest-risk piece, solved first, with hours of runway left if it's flaky. |
| **Offline reasoning brain** | Gemini (Flash / Flash-Lite, Developer API free tier) | Everything that isn't the live call — JD/resume parsing, gap analysis, question planning, scoring — also runs on Gemini's free tier, not a paid key. The Anthropic API has no ongoing free tier (only a one-time ~$5 trial credit on new accounts), so keeping the whole stack on Gemini matches the "free tiers only, zero cost" constraint cleanly. **Caveat:** free-tier limits are per-project, shared with the Live API call — prep + scoring + 5 eval personas is only ~15–30 calls total for the day, well inside the ceiling, but avoid firing them in a tight concurrent burst. If Flash's structured-output reliability gets flaky under time pressure, Flash-Lite has a slightly higher RPM ceiling as a same-provider fallback — no new key needed either way. |
| **Transport** | LiveKit Cloud (Build/free tier) | Free tier: 1,000 agent-session minutes/mo, 5,000 WebRTC minutes, $2.50 inference credit, no card required. Comfortably covers a full day of test calls plus the real interview. Has first-party plugins for avatar vendors if you ever want to swap in a real one later — config change, not a rewrite. |
| **Avatar** | 2D portrait + viseme lip-sync, driven by TTS/audio stream | The spec states this explicitly earns **full marks** on requirement #1. Pure frontend (canvas/CSS timed off phoneme or amplitude data) — zero API cost, zero credential to protect, zero vendor to be down on demo day. Nothing to swap in later unless you want to for polish. |
| **Graph** | LangGraph + SQLite checkpointer | As specified. Typed state, 6+ nodes, 2+ conditional edges, checkpointer so a dropped call resumes mid-node. |
| **GitHub grounding** | GitHub REST API + free PAT (5,000 req/hr) | Authenticated PAT from hour 0 — don't build against the 60/hr unauthenticated limit and hit a wall later. Cache responses hard; you'll re-run the same repo lookups while debugging. |
| **Resume/JD parsing** | pdfplumber (or pypdf) → Claude structured output | Structured JSON, no manual field entry — required by #3. |
| **MCP server** | fastmcp (Python), stdio transport | **This never needs to be deployed anywhere.** Claude Desktop launches it as a local subprocess. Zero deployment risk for 8 of your 100 marks, regardless of what happens with the rest of the infra. |
| **Report** | reportlab or WeasyPrint | Pure Python, no external service. |
| **Deployment (core)** | **Split the system — see §3** | Agent worker runs locally (your laptop, connected to LiveKit Cloud). Only a thin static join-page needs a public link. |
| **Deployment (bonus only)** | Render, attempted last | Railway's permanent free tier is gone (removed 2024). Render's free web-service tier sleeps after 15 min idle with a 30–50s cold start — fine for a bonus static demo, unacceptable for anything that must be live-connected during a call. Don't let this bonus item touch your core-path architecture. |

### Why the deployment split matters
The doc's own "Deploy" row (Render/Railway free tier, fallback localhost — bonus mark only) already tells you the graders don't expect your *agent* to be hosted. Read literally: only **requirement bonus #5 (Deployed live URL, 5 marks)** cares about a public backend. None of the 12 core requirements need it. So:

- **Agent worker** (LangGraph + Gemini Live + guardrails + avatar renderer) — runs on your machine, dials outbound to LiveKit Cloud. This *is* the correct architecture, not a shortcut.
- **Candidate join page** — a static page using LiveKit's JS client SDK. Deploy free and always-on to Vercel/Netlify/Cloudflare Pages — no sleep, no cold start, this is the one link you actually hand to your candidate.
- **MCP server** — local stdio subprocess, launched by Claude Desktop. Never deployed.
- Only attempt containerizing the agent worker for Render **after** all 12 core requirements and both required videos are done, purely for the bonus mark.

---

## 3. Repo Structure

Exact paths from the spec's §6 — automated grading reads these; wrong path = zero for that item.

```
firstround/
├── README.md              # run it in <5 steps
├── ARCHITECTURE.md         # graph diagram, state object, MEASURED latency, known limits
├── SUBMISSION.md           # one page: links, what works, what's broken, barge-in
│                          # timestamp, JD chosen, latency, avatar used, bonus
│                          # attempted, candidate consent line
├── .env.example            # key NAMES only — never a real key
├── src/
│  ├── graph.py             # state, nodes, edges
│  ├── nodes/               # one file per LangGraph node
│  ├── agents/              # github_agent.py, resume_parser.py, jd_parser.py,
│  │                       # question_planner.py, scorer.py
│  ├── realtime/            # transport (LiveKit), avatar (2D lip-sync), barge-in
│  └── guardrails/           # banned_questions.py, evidence_check.py
├── mcp_server/              # fastmcp, ≥5 tools
├── prompts/                 # one file per system prompt + ITERATION_NOTES.md
├── evals/
│  ├── personas/             # 5 synthetic transcripts
│  └── run_evals.py, results.md
├── inputs/                  # jd.txt, resume.pdf
└── output/
   ├── prep/                 # jd.json, resume.json, github.json, question_plan.json
   ├── transcript.json
   ├── scorecard.json
   └── report.pdf
```

---

## 4. Fixed Schemas (do not deviate — extra fields OK, missing fields are not)

**`output/scorecard.json`**
```json
{ "candidate_name": "", "role": "",
  "interview_date": "YYYY-MM-DD", "duration_seconds": 0,
  "competencies": [
    { "name": "", "score": 3,
      "confidence": 0.0,
      "evidence_quote": "",
      "reasoning": "" } ],
  "overall_score": 0.0,
  "recommendation": "hire",
  "recommendation_reasoning": "",
  "strengths": [], "concerns": [],
  "guardrail_flags": [],
  "github_grounded_questions_asked": 0 }
```

**`output/transcript.json`**
```json
{ "turns": [ { "speaker": "agent",
    "text": "", "timestamp_ms": 0,
    "node": "github_deepdive", "interrupted": false } ] }
```

**`output/prep/question_plan.json`**
```json
{ "questions": [ { "id": "q1", "text": "", "competency": "",
    "source": "github",
    "source_reference": "repo/file/commit or resume line",
    "difficulty": "medium",
    "follow_up_triggers": [] } ],
  "approved_by_human": true, "edits_made": [] }
```

---

## 4B. MCP Tool Contracts (requirement #8 — the 5 required tools)

These 5 are the mandatory set named in the spec — build exactly these, no substitutions, no extras needed to hit the mark:

| Tool | Input | Output | Reads/writes |
|---|---|---|---|
| `get_candidate` | `candidate_id` | name, role, resume summary, GitHub handle | `output/prep/resume.json` |
| `get_question_plan` | `interview_id` | the approved question plan | `output/prep/question_plan.json` |
| `save_score` | `interview_id, competency, score, confidence, evidence_quote, reasoning` | write confirmation | appends into `output/scorecard.json`, rejects if `evidence_quote` is empty (this is where guardrail #9b actually lives) |
| `get_scorecard` | `interview_id` | the full scorecard | `output/scorecard.json` |
| `list_interviews` | *(none)* | interview IDs + candidate name + status | scans `output/` |

FastMCP 3.x, unchanged decorator pattern, still the right call:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("firstround")

@mcp.tool()
def get_scorecard(interview_id: str) -> dict:
    """Return the full scorecard for a completed interview."""
    ...

if __name__ == "__main__":
    mcp.run(transport="stdio")   # local — this is the only transport you need
```

Register it in Claude Desktop's config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS, `%APPDATA%\Claude\claude_desktop_config.json` on Windows) pointing at this script. Test each tool from the Claude Desktop chat itself before recording the required screenshot — the proof is "verified working inside Claude Desktop," not just unit-tested in isolation.

---

## 5. Core Requirements Checklist (all 12 required — this is your Definition of Done for Phase A)

| # | Requirement | Acceptance test |
|---|---|---|
| 1 | Live video call, visible face | 8+ min continuous, 2D avatar lip-synced to real TTS audio, raw recording saved |
| 2 | Barge-in | Candidate cuts in mid-sentence → agent stops instantly, no talk-over. Timestamped in SUBMISSION.md |
| 3 | JD + resume parsing | PDF → structured JSON, zero manual field entry, survives a messy PDF |
| 4 | GitHub grounding | ≥3 questions cite a specific repo/file/commit, genuinely specific (not generic) |
| 5 | LangGraph structure | Typed state, ≥6 nodes, ≥2 conditional edges, SQLite checkpointer resumes a dropped call |
| 6 | Adaptive follow-up | Shallow answer → probe (max 2, then move on); strong answer → difficulty rises |
| 7 | HITL gate | Graph genuinely pauses; approve / edit / reject all functionally work |
| 8 | MCP server | ≥5 tools, correct schemas, verified working *inside Claude Desktop* |
| 9 | Guardrails | Banned-topic questions blocked before reaching candidate; no score without a transcript quote; both proven by a test |
| 10 | Scorecard | Matches §4 schema, real quotes, sensible recommendation |
| 11 | Evals | 5 personas ranked correctly (Strong > Nervous ≈ near-Strong > Average > Bluffer > Weak), honest failure notes |
| 12 | Prompts as files | Every system prompt its own file + v1→v2 notes with a real diagnosed failure |

---

## 5B. Rubric Mapping (verified against the official 100-point rubric)

| Rubric item | Marks | Earned in |
|---|---|---|
| Live video call + face | 10 | Phase 0.5–2 (built), Phase 8 (proof recording) |
| Barge-in & turn-taking | 5 | Phase 0.5–2 |
| JD + resume parsing | 5 | Phase 2–3.5 |
| GitHub grounding | 10 | Phase 2–3.5 |
| LangGraph structure | 10 | Phase 3.5–5 |
| Adaptive follow-up | 7 | Phase 3.5–5 |
| HITL gate | 5 | Phase 5–6.5 |
| MCP server | 8 | Phase 5–6.5 |
| Guardrails | 5 | Phase 6.5–7.5 |
| Scorecard | 5 | Phase 6.5–7.5 |
| Evals | 8 | Phase 7.5–8 |
| Prompt engineering | 4 | Phase 8.5–9 |
| Architecture docs | 4 | Phase 8.5–9 |
| Repo hygiene | 4 | **Continuous — not a single phase** |
| Code video | 4 | Phase 9–9.75 |
| Demo video | 4 | Phase 9–9.75 |
| SUBMISSION.md | 2 | Phase 8.5–9 |

**Two things this mapping surfaces that the hour blocks alone don't show:**
- **Repo hygiene (4 marks) needs 10+ commits spread across the whole day**, not one at the end. Commit after each phase block as a habit, not a cleanup step — it costs nothing if done as you go and is awkward to fake retroactively.
- **Phase 8.5–9 is carrying 10 rubric marks (architecture docs + prompt notes + SUBMISSION.md) in 30 minutes.** Writing all three from a blank page in that window is tight. Cheaper fix: jot one or two lines into `ARCHITECTURE.md` and `prompts/ITERATION_NOTES.md` right after each phase actually happens (e.g., the measured latency number the moment you have it, the prompt v1→v2 diagnosis the moment you hit it) — Phase 8.5–9 then becomes assembling and polishing notes that already exist, not drafting from zero.

---

## 6. Phased Build Plan

### 6A. Active plan — 10-hour compressed track

This is the real working budget. All bonus tiers are cut — there's no honest way to fit one in 10 hours alongside all 12 core requirements. Evals stay in (they're core requirement #11, not optional) but lean. No slack anywhere: if Gemini Live's known mid-sentence cutoff bug shows up, or the interview needs a second take, something else on this list gets cut, not added around.

**Candidate for the real interview: self.** No partner locked to this exact window, so the agent interviews the builder. Documented as an explicit, honest choice in SUBMISSION.md rather than hidden — this is a disclosed constraint, not a shortcut.

| Hours | Block |
|---|---|
| 0–0.5 | Keys verified, current Gemini Live model ID confirmed in AI Studio, repo scaffolded |
| 0.5–2 | Joinable call + barge-in working — still the highest-risk piece, no shortcut |
| 2–3.5 | Prep graph: parse_jd, parse_resume, github_agent, gap_analysis, question_planner |
| 3.5–5 | LangGraph: nodes, conditional edges, SQLite checkpointer |
| 5–6.5 | 2D avatar wired to TTS, HITL gate, MCP server (5 tools, tested live in Claude Desktop) |
| 6.5–7.5 | Scorecard + both guardrails, with tests proving each fires |
| 7.5–8 | 5 eval personas run through the real scorer — lean, but the ranking table and failure notes still need to be honest |
| 8–8.5 | The real interview — self as candidate, real consent line still written into SUBMISSION.md, recorded in one take |
| 8.5–9 | ARCHITECTURE.md, SUBMISSION.md, prompt ITERATION_NOTES.md — written in parallel with whatever's exporting/rendering |
| 9–9.75 | Both videos — scripted before recording, one take each |
| 9.75–10 | Clean-clone test, confirm `.env` isn't committed, submit |

If any block runs long, the order of what gets dropped first: bonus (already cut) → video editing polish → eval persona depth (keep the ranking, thin the write-up) → never the guardrail tests, the checkpointer-resume proof, or the consent line. Those three are the ones a viva question or a hidden grading script will actually catch.

### 6B. Reference plan — full 24-hour track (fallback if time opens back up)

Adjusted from the spec's own 24-hour plan to front-load the two genuinely fragile pieces (Gemini Live stability, HITL/checkpointer correctness) and to never let deployment plumbing block a core-path hour.

**Phase 0 — Keys & scaffolding (0–1h)**
Verify every API key works with a throwaway call: Gemini Live, Claude/Anthropic, GitHub PAT. Confirm the *current* Gemini Live model ID in AI Studio — do not hardcode from memory or an old tutorial. Scaffold the repo tree from §3.

**Phase 1 — Joinable call (1–3h)**
LiveKit room + Gemini Live audio in/out, plain placeholder visual (no avatar yet). Goal: an AI voice that speaks, listens, and interrupts cleanly. This is the doc's own "highest-risk piece, solve it first" — if Gemini Live's mid-sentence cutoff bug shows up, you find out here with 20 hours left, not at hour 15.

**Phase 2 — Prep graph, offline (3–5h)**
`parse_jd → parse_resume → github_agent → gap_analysis → question_planner`. Output the four `prep/*.json` files. This is fully testable without touching the live call at all — good place to validate Claude's structured-output reliability.

**Phase 3 — LangGraph assembly (5–7h)**
Full graph: intro → resume_probe → jd_fit → github_deepdive → scenario → candidate_Qs → wrap_up, with the conditional edges (shallow/strong/bluff/silence/time-out) and the SQLite checkpointer. Kill the checkpointer mid-call on purpose and confirm it resumes at the right node.

**Phase 4 — Avatar, HITL, MCP (7–9h)**
2D lip-sync avatar wired to the TTS stream. HITL interrupt: recruiter approve/edit/reject, all three paths actually exercised. `mcp_server/` with 5 tools, tested live inside Claude Desktop — not just unit-tested in isolation.

**Phase 5 — Scorecard & guardrails (9–11h)**
Scoring node, evidence-quote enforcement (`score without quote → rejected`), banned-question blocklist with a test proving both guardrails fire.

**Phase 5.5 — Sleep (11–13h)**
Non-negotiable. You're recording your own voice as the interviewer/candidate tomorrow.

**Phase 6 — Evals (13–15h)**
Write the 5 synthetic transcripts (Strong, Average, Weak, Bluffer, Nervous), run them through the real scorer, record the ranking table. If the bluffer doesn't land below Average or the nervous persona doesn't land near Strong — that's the interesting finding, write it down honestly rather than tuning the eval until it looks clean.

**Phase 7 — The real interview (15–17h)**
8+ minutes, real classmate/partner, real consent obtained first. Budget for two takes.

**Phase 8 — Bonus (17–19h)** — see §7. Only if Phase 0–7 is fully done.

**Phase 9 — Docs (19–21h)**
ARCHITECTURE.md (diagram matching actual code, *measured* not guessed latency, stated limitations), prompts/ITERATION_NOTES.md, README (clean-clone test), SUBMISSION.md.

**Phase 10 — Videos (21–23h)**
Script both before recording — 60s and 90s are shorter than they feel. Code video: graph, one conditional edge, MCP tools, one guardrail firing. Demo video: avatar speaking, a barge-in moment, a GitHub-grounded question, final scorecard.

**Phase 11 — Clean-clone test, submit (23–24h)**
Fresh clone, README works standalone, video links tested in a private window, `.env` confirmed absent from the repo, submit, book the viva slot.

### 6C. LangGraph Starter Skeleton (for Phase 3.5–5 / 6B-Phase 5–7h)

Current package + import (verified — the old `SqliteSaver` import path from pre-2024 tutorials moved into its own package):

```bash
pip install langgraph langgraph-checkpoint-sqlite
```

```python
from typing import TypedDict, Literal
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver  # async — matches an async LiveKit call loop

class InterviewState(TypedDict):
    candidate: dict
    question_plan: list[dict]
    current_question_idx: int
    transcript: list[dict]
    probe_count: dict[str, int]      # per-competency, caps adaptive follow-up at 2
    difficulty: str
    guardrail_flags: list[str]
    time_elapsed_s: int

builder = StateGraph(InterviewState)

# 7 nodes — clears the "6+ nodes" bar with room to spare
for node_name in ["intro", "resume_probe", "jd_fit", "github_deepdive",
                   "scenario", "candidate_qs", "wrap_up"]:
    builder.add_node(node_name, globals()[f"node_{node_name}"])  # implement each in src/nodes/

builder.add_edge(START, "intro")

def route_after_answer(state: InterviewState) -> Literal["follow_up", "raise_difficulty", "verify", "recovery", "wrap_up", "next_question"]:
    # shallow -> follow_up (capped at 2 via probe_count)
    # strong -> raise_difficulty
    # bluff detected -> verify ("walk me through that commit")
    # silence/off-topic -> recovery
    # time_elapsed_s over budget -> wrap_up
    ...

# attach route_after_answer as a conditional edge off each interview-content node —
# this is where the "2+ conditional edges" requirement is actually earned, and where
# the adaptive-follow-up rubric line (7 marks) lives

graph = builder.compile(checkpointer=None)  # swap in AsyncSqliteSaver at runtime, see below

# runtime wiring — this is what makes checkpoint-resume actually testable in Phase 3.5-5
async def run():
    async with AsyncSqliteSaver.from_conn_string("checkpoints.db") as checkpointer:
        app = builder.compile(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": "interview-1"}}
        await app.ainvoke(initial_state, config)
        # kill this process mid-call on purpose, then re-run with the same thread_id —
        # it should resume at the last node, not restart. That's your Phase 3.5-5 acceptance test.
```

Note in the code comments above the SQLite checkpointer docs' own caution: it's meant for local dev/demo scale, not production write concurrency — exactly this project's situation, so no action needed, just don't be surprised if a blog post warns you off it for a "real" deployment.

---

## 7. Bonus Modules — only after all 12 core items are solid

Rubric math favors depth over breadth: **one Tier 2 (10 marks) beats two Tier 1 (5 each)** in terms of what it signals about your engineering judgement, even though the raw points are equal — a Tier 2 item forces a harder demonstration of correctness (drift tables, ranking calibration) that's much more visible in the viva.

Given the JD (Junior AI Engineer) and the 2D-avatar choice already made, the best-fit bonus is:

- **Bias audit (Tier 2, 10 marks)** — re-score the same transcript with name/gender swapped, report the drift, flag anything over 0.5. Natural extension of the scoring pipeline you already built for the core scorecard — low net-new surface area, high signal.
- If time remains after that: **Deployed live URL (Tier 1, 5 marks)** — the one bonus that touches the deployment split in §2, attempted last, accepting Render's cold-start caveat since it's not on the critical path.

Skip live coding round / recruiter live-join / reference-check / Urdu code-switch / multi-candidate ranking for this cycle — each adds a genuinely new subsystem under time pressure, which is the opposite of what a 24-hour budget rewards.

---

## 8. Guardrails Spec (requirement #9)

- **Banned-topic blocklist**, checked *before* a question reaches the candidate: age, gender, marital status, religion, nationality, health/pregnancy, salary history, politics.
- **Evidence-check guardrail**: any competency score without a matching transcript quote is rejected at the scoring node, not silently defaulted.
- Both need an actual test file proving they fire — not just a code comment claiming they do.

---

## 9. Secrets & Deployment Hygiene

- `.env.example` ships key *names* only. `.env` itself is git-ignored from commit 1, not added later.
- A committed real key is –5 marks and a forced rotation — check this explicitly before the Phase 11 clean-clone test.
- Because the agent worker runs locally and the MCP server is stdio-local, your actual attack surface for "oops, deployed a key" is just the static join-page repo — keep that one dead simple (no server-side secrets at all, it only needs a LiveKit room token endpoint, which itself can be a small local/serverless function).

### 9B. Where to Get Each Key

Only 3 credentials needed for the whole app, since the stack is fully free-tier. Claude Code itself authenticates with your own Claude.ai/Console login — that's not a project secret and doesn't go in `.env`.

| Env var | Where to get it | Used for | Notes |
|---|---|---|---|
| `GEMINI_API_KEY` | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) — sign in with Google, "Create API key," no card required | Gemini Live (realtime call) **and** Gemini Flash/Flash-Lite (offline parsing, planning, scoring) | One key covers both — free tier, rate limits are per-project, shared across both uses |
| `LIVEKIT_URL` | [cloud.livekit.io](https://cloud.livekit.io) — create a project → Settings → Project → the `wss://...` URL | LiveKit room connection | Free Build tier |
| `LIVEKIT_API_KEY` + `LIVEKIT_API_SECRET` | Same LiveKit project → Settings → Keys → Create key | Server-side room token generation | The secret is shown once — copy it immediately, LiveKit won't display it again |
| `GITHUB_TOKEN` | [github.com/settings/tokens](https://github.com/settings/tokens) → Generate new token (classic) → scope `public_repo` (use `repo` if the candidate's repos are private) | GitHub REST grounding | Authenticated = 5,000 req/hr vs. 60/hr unauthenticated. Get this in Phase 0, not after hitting the wall in Phase 2 |

`.env.example` (commit this — names only, no real values):
```
GEMINI_API_KEY=
LIVEKIT_URL=
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=
GITHUB_TOKEN=
```

Copy to `.env`, fill in real values, confirm `.env` is in `.gitignore` before the first commit — not after.

---

## 10. Risk Register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Gemini Live cuts off mid-sentence (known open bug) | Medium | Solved in Phase 1 with 20h of runway left; if unworkable, fallback is Groq Whisper STT + LLM + TTS pipeline per the doc's own fallback column — same core requirements, more code to write |
| Gemini Live model ID deprecated between now and demo day | Low-Medium | Pull current model ID from AI Studio at build time, don't hardcode from memory |
| LangGraph presented as a graph but is secretly linear | Medium (self-inflicted) | Conditional edges must be exercised by real test cases, not just present in code — this halves your LangGraph marks if faked |
| Checkpointer doesn't actually resume | Medium | Explicitly kill the process mid-call in Phase 3 and verify resume, don't assume |
| Running out of time for both required videos | Medium | Scripts written before recording, in Phase 9, not improvised in Phase 10 |
| Real API key committed | Low if disciplined | `.env` git-ignored from commit 1; explicit check in Phase 11 |
| "Self as candidate" isn't explicitly sanctioned by the doc (only classmate/friend/family named) | Low-Medium | Send a quick check to the instructor/aiseason.tech channel in parallel with building, don't block on the reply; disclose the choice plainly in SUBMISSION.md either way |

---

## 11. UI Reference (defer to Phase 9 polish window — single screen only)

Reference: uploaded live-interview dashboard mockup — photorealistic avatar panel, current-question caption, mic/barge-in/camera controls, live transcript sidebar, and four bottom cards (candidate info, current question, round progress, live scoreboard).

**Build only the single live-call screen** — avatar panel, control bar, current-question caption, the four bottom cards, transcript sidebar if time allows. **Skip the sidebar nav entirely** (Dashboard/Candidates/Question Plans/Interviews/Practice/Reports/Settings) — a multi-page SaaS shell with zero attached rubric marks.

Two functional details, not just visual ones:
- *"Tap to Speak"* must not become the primary interaction model — barge-in (5 marks) needs continuous open-mic listening with Gemini Live's native VAD interruption. A tap affordance is fine as a secondary control only.
- *Live Scoreboard* mid-call isn't a rubric item. If built, derive it from the same lightweight per-turn evaluator already needed for shallow/strong conditional routing — don't build a second scoring pipeline. The real `scorecard.json` still computes properly after the call with the evidence-quote guardrail enforced.

Not shown in this reference, still required: the HITL approve/edit/reject screen (Phase 1, pre-call) — a separate, simpler screen.

---

## Open items to line up before Phase 8 (10h track) — logistics, not architecture
- **Candidate = self** for the real interview (no partner available in the 10h window). Still needs a real resume and GitHub profile behind it — already true, since it's yours.
- Still write an explicit **consent line** into SUBMISSION.md even though you're both parties — keeps the deliverable format identical to what a grading script expects to find.
- If a classmate/partner becomes available before Phase 8, swap them in — a second real candidate is strictly stronger evidence for "would a real candidate believe they were being interviewed" than a self-interview, so it's worth a last-minute swap if the window opens up.
