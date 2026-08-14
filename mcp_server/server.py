"""FirstRound MCP server -- requirement #8, the 5 required tools.

Local stdio subprocess, launched by Claude Desktop. Never deployed (see
PRD section 2). Single-candidate/single-interview scope matches the
actual project (self-as-candidate, one real interview) -- interview_id/
candidate_id params exist for interface compliance with the PRD's tool
contracts, but resolve to the one canonical set of files under output/,
not a multi-tenant store.
"""

import json
from datetime import date
from pathlib import Path

from fastmcp import FastMCP

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
PREP = OUTPUT / "prep"

INTERVIEW_ID = "interview-1"

mcp = FastMCP("firstround")


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


@mcp.tool()
def get_candidate(candidate_id: str) -> dict:
    """Return name, role, resume summary, and GitHub handle for a candidate."""
    resume = _read_json(PREP / "resume.json")
    jd = _read_json(PREP / "jd.json")
    if resume is None:
        return {"error": f"No resume found (looked in {PREP / 'resume.json'}). Run the prep pipeline first."}
    return {
        "candidate_id": candidate_id,
        "name": resume["name"],
        "role": jd["title"] if jd else "unknown",
        "resume_summary": resume["summary"],
        "github_handle": resume["github_handle"],
    }


@mcp.tool()
def get_question_plan(interview_id: str) -> dict:
    """Return the approved question plan for an interview."""
    plan = _read_json(PREP / "question_plan.json")
    if plan is None:
        return {"error": f"No question plan found (looked in {PREP / 'question_plan.json'}). Run question_planner first."}
    return plan


@mcp.tool()
def save_score(
    interview_id: str,
    competency: str,
    score: int,
    confidence: float,
    evidence_quote: str,
    reasoning: str,
) -> dict:
    """Save a competency score to the scorecard. Rejects the write if
    evidence_quote is empty -- this is where guardrail #9b (no score
    without a transcript quote) actually lives, per the PRD's own tool
    contract."""
    if not evidence_quote or not evidence_quote.strip():
        return {
            "status": "rejected",
            "reason": "evidence_quote is required -- no score without a real transcript quote (guardrail #9b)",
        }

    scorecard_path = OUTPUT / "scorecard.json"
    scorecard = _read_json(scorecard_path)
    if scorecard is None:
        resume = _read_json(PREP / "resume.json")
        jd = _read_json(PREP / "jd.json")
        scorecard = {
            "candidate_name": resume["name"] if resume else "",
            "role": jd["title"] if jd else "",
            "interview_date": date.today().isoformat(),
            "duration_seconds": 0,
            "competencies": [],
            "overall_score": 0.0,
            "recommendation": "",
            "recommendation_reasoning": "",
            "strengths": [],
            "concerns": [],
            "guardrail_flags": [],
            "github_grounded_questions_asked": 0,
        }

    entry = {
        "name": competency,
        "score": score,
        "confidence": confidence,
        "evidence_quote": evidence_quote,
        "reasoning": reasoning,
    }
    existing = [c for c in scorecard["competencies"] if c["name"] == competency]
    if existing:
        scorecard["competencies"] = [entry if c["name"] == competency else c for c in scorecard["competencies"]]
    else:
        scorecard["competencies"].append(entry)

    _write_json(scorecard_path, scorecard)
    return {"status": "saved", "interview_id": interview_id, "competency": competency}


@mcp.tool()
def get_scorecard(interview_id: str) -> dict:
    """Return the full scorecard for a completed interview."""
    scorecard = _read_json(OUTPUT / "scorecard.json")
    if scorecard is None:
        return {"error": f"No scorecard found for {interview_id} yet -- call save_score first."}
    return scorecard


@mcp.tool()
def list_interviews() -> list[dict]:
    """List interview IDs, candidate name, and status."""
    resume = _read_json(PREP / "resume.json")
    plan = _read_json(PREP / "question_plan.json")
    scorecard = _read_json(OUTPUT / "scorecard.json")

    if resume is None and plan is None and scorecard is None:
        return []

    if scorecard is not None:
        status = "scored"
    elif plan is not None:
        status = "planned"
    else:
        status = "prepped"

    return [
        {
            "interview_id": INTERVIEW_ID,
            "candidate_name": resume["name"] if resume else "unknown",
            "status": status,
        }
    ]


if __name__ == "__main__":
    mcp.run(transport="stdio")
