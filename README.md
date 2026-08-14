# FirstRound — AI Video Interviewer

See `PRD.md` for full architecture rationale and `ARCHITECTURE.md` for the
as-built graph/state/latency notes and known limitations.

## Setup

1. `python -m venv .venv && .venv\Scripts\activate` (Windows)
2. `pip install -r requirements.txt`
3. `copy .env.example .env` and fill in real values (see PRD §9B for where
   to get each key — all free tier, no card required)
4. Verify keys:
   `python scripts/verify_gemini.py`, `python scripts/verify_livekit.py`,
   `python scripts/verify_github.py`

## Run: offline prep pipeline

Produces `output/prep/*.json` from real inputs (`inputs/jd.txt`,
`inputs/resume.pdf`, and the GitHub handle in the parsed resume):

```
python -m src.agents.jd_parser
python -m src.agents.resume_parser
python -m src.agents.github_agent <github-handle>
python -m src.agents.question_planner
```

Then review/approve the plan (approve, edit specific questions, or
reject — all three genuinely pause the graph and resume it, requirement
#7):

```
python -m src.hitl
```

## Run: tests and evals

```
python -m src.graph_test          # scripted interview, checkpoint kill-and-resume proof
python -m src.hitl_test           # approve/edit/reject, scripted
python -m src.guardrails_test     # both guardrails, proven to fire
python -m evals.run_evals         # 5 personas through the real scorer -> evals/results.md
```

## Run: MCP server

Register in Claude Desktop's config (path is MSIX-virtualized on this
machine — see `ARCHITECTURE.md` Phase 4 — otherwise
`%APPDATA%\Claude\claude_desktop_config.json`):

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

Restart Claude Desktop, then ask it to call `list_interviews`,
`get_candidate`, `get_question_plan`, `save_score`, or `get_scorecard`.

## Run: the live interview

Three pieces, all local:

1. **Agent worker** (Python, connects outbound to LiveKit Cloud):
   ```
   python -m src.realtime.agent dev
   ```
2. **Mint a room + dispatch + join token** (no recording, avoids the
   LiveKit Cloud Console overhead noted in `ARCHITECTURE.md` Phase 1):
   ```
   python scripts/mint_lean_room.py
   ```
3. **Join page**: open the `web/join.html?...` link the script prints,
   click Connect once. Shows the 2D avatar lip-synced to the agent's
   real TTS audio, live-driven from the interview graph
   (`src/graph.py` via `src/realtime/orchestrator.py`).

**Known issue, not eliminated:** the room-connect step intermittently
fails with a native FFI timeout specific to this dev machine's CPU (see
`ARCHITECTURE.md` Phase 1 and Phase 7) — if the agent doesn't speak
within ~30s of connecting, kill the worker, rerun step 1, and mint a
fresh room. This is an upstream `livekit/rust-sdks` issue, not a bug in
this codebase.

After the interview ends, score it:

```
python -m src.agents.scorer
```

Writes `output/scorecard.json` from `output/transcript.json`.

## Repo structure

See `PRD.md` §3 for the intended layout; matches as-built.
