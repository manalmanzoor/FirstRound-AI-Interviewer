# Video Scripts

Scripted before recording per the plan (PRD §10 in the 24h reference,
§9-9.75 in the 10h track) -- shorter than they feel, read through once
before hitting record.

---

## Code Walkthrough Video (~4 min)

**Goal:** prove you understand and could modify every piece live.

1. **Repo structure (30s)** — open the repo root, walk through
   `src/graph.py`, `src/nodes/`, `src/agents/`, `src/guardrails/`,
   `src/realtime/`, `mcp_server/`, `prompts/`, `evals/`. One sentence
   each on what lives where.

2. **The graph (60s)** — open `src/graph.py`. Show `InterviewState`,
   the 7 nodes, and point at the 4 `add_conditional_edges` calls. Explain
   `make_route_after_answer(source)` is a factory (one closure per
   content node), not one shared function — and why: each node needs to
   know its own source to decide "stay" vs "advance." Mention the node
   order deviation (`github_deepdive` first, not third) and why —
   time-budget expiry silently zeroed out GitHub questions in the first
   real interview.

3. **One conditional edge in action (45s)** — open `src/nodes/_content_node.py`.
   Show `is_follow_up` and explain the real bug that lived there: probe
   count only increments when `is_follow_up` mirrors the routing
   function's own predicate exactly, because the original version (keyed
   off `asked_question_ids` membership) silently broke the follow-up loop
   entirely. This is a good "I can explain what actually went wrong"
   moment for the viva.

4. **MCP tools (45s)** — switch to Claude Desktop, open a chat, call
   `list_interviews` and `get_scorecard` live. Show `mcp_server/server.py`
   briefly, point at `save_score`'s evidence_quote rejection.

5. **A guardrail firing (45s)** — run
   `python -m src.guardrails_test` on screen, point at the banned-topic
   and evidence-check assertions passing. Briefly show
   `src/guardrails/banned_questions.py`'s regex table.

6. **Close (15s)** — one sentence on what you'd do with another hour
   (e.g. fix the residual transcription-language issue, or migrate off
   the deprecated `allow_interruptions`/`discard_audio_if_uninterruptible`
   params to `turn_handling=TurnHandlingOptions(...)`).

---

## Demo Video (~90s)

**Goal:** "would a real candidate believe they were being interviewed?"

1. **Avatar + intro (15s)** — show the join page connecting, avatar
   mouth moving in sync as the agent greets the candidate.

2. **A GitHub-grounded question (20s)** — let it ask one of the
   real questions citing a specific repo/file/commit (e.g. the
   `RAG-RedTeam-Toolkit commit d61cdca1` question). This is the clearest
   single proof of requirement #4.

3. **Barge-in (15s)** — interrupt it mid-sentence. Let the cut-off be
   visible/audible in the recording — this is the actual proof for
   requirement #2, not just a claim in SUBMISSION.md.

4. **Adaptive follow-up (20s)** — if you gave a shallow answer anywhere
   in the real take, show the follow-up question landing. If not
   available in the real footage, this is fine to note honestly as
   "demonstrated separately in graph_test.py output" rather than fake it.

5. **Final scorecard (20s)** — show `output/scorecard.json`, scroll to
   one competency with its real evidence_quote, and the overall
   recommendation.

**Note for both:** if the final real interview still has the
transcription-language glitch (Phase 7's ARCHITECTURE.md note), don't
edit around it — mention it in one sentence on camera. The PRD is
explicit that honest limitations score better than a suspiciously clean
take.
