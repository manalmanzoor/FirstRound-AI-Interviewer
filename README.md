# FirstRound — AI Video Interviewer

See `PRD.md` for full architecture rationale and `ARCHITECTURE.md` for the
as-built graph/state/latency notes.

## Setup

1. `python -m venv .venv && .venv\Scripts\activate` (Windows)
2. `pip install -r requirements.txt`
3. `copy .env.example .env` and fill in real values (see PRD §9B for where
   to get each key — all free tier, no card required)
4. Verify keys: `python scripts/verify_gemini.py`, `python scripts/verify_livekit.py`,
   `python scripts/verify_github.py`
5. _(filled in as each phase lands: how to run the agent worker, the join page, the MCP server)_

## Run

_(filled in during later phases)_
