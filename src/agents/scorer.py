"""scorer: transcript.json + question_plan.json -> output/scorecard.json
(requirement #10, PRD section 4 schema).

The single most important instruction in this module's prompt is the one
about bluffing vs nervousness (PRD section 1): "a confident bluffer must
score below a nervous-but-correct candidate." Fluency and confidence are
explicitly NOT the signal to score on -- technical substance is. Every
guardrail_flags entry logged live during the interview (possible_bluff:*
from src/nodes/_content_node.py) is passed in and must pull that
competency's score down, not get silently ignored.
"""

import json
from datetime import date
from pathlib import Path

from src.prompts import load_prompt

from .gemini import structured
from .guardrails_bridge import validate_scorecard_evidence
from .schemas import Scorecard

ROOT = Path(__file__).resolve().parents[2]

PROMPT_TEMPLATE = load_prompt("scorer")


def score_interview(
    transcript_path: Path | None = None,
    question_plan_path: Path | None = None,
    resume_path: Path | None = None,
    jd_path: Path | None = None,
    output_path: Path | None = None,
) -> tuple[Scorecard, list[str]]:
    transcript_path = transcript_path or ROOT / "output" / "transcript.json"
    question_plan_path = question_plan_path or ROOT / "output" / "prep" / "question_plan.json"
    resume_path = resume_path or ROOT / "output" / "prep" / "resume.json"
    jd_path = jd_path or ROOT / "output" / "prep" / "jd.json"
    output_path = output_path or ROOT / "output" / "scorecard.json"

    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    question_plan = json.loads(question_plan_path.read_text(encoding="utf-8"))
    resume = json.loads(resume_path.read_text(encoding="utf-8"))
    jd = json.loads(jd_path.read_text(encoding="utf-8"))

    # guardrail_flags and github_grounded_questions_asked live on the
    # live interview's graph state, not in transcript.json or the
    # question plan -- when driven by src/graph.py these get passed
    # through by the caller (see graph_test.py / the real agent
    # integration); default to empty/0 when scoring a bare transcript.
    guardrail_flags = transcript.get("guardrail_flags", [])
    github_grounded_questions_asked = transcript.get("github_grounded_questions_asked", 0)
    duration_seconds = transcript.get("duration_seconds", 0)

    prompt = PROMPT_TEMPLATE.format(
        candidate_name=resume["name"],
        role=jd["title"],
        guardrail_flags=json.dumps(guardrail_flags),
        github_grounded_questions_asked=github_grounded_questions_asked,
        question_plan_json=json.dumps(question_plan["questions"], indent=2),
        transcript_json=json.dumps(transcript["turns"], indent=2),
    )
    scorecard = structured(prompt, Scorecard)
    scorecard.guardrail_flags = guardrail_flags
    scorecard.github_grounded_questions_asked = github_grounded_questions_asked
    scorecard.duration_seconds = duration_seconds
    # The model has no reliable notion of "today" and was observed
    # inventing a plausible-looking but wrong date -- set programmatically.
    scorecard.interview_date = date.today().isoformat()

    warnings = validate_scorecard_evidence(scorecard, transcript["turns"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(scorecard.model_dump(), indent=2), encoding="utf-8")
    return scorecard, warnings


if __name__ == "__main__":
    scorecard, warnings = score_interview()
    print(f"OK  scored {scorecard.candidate_name} for {scorecard.role}")
    print(f"    overall_score={scorecard.overall_score}, recommendation={scorecard.recommendation}")
    for c in scorecard.competencies:
        print(f"    [{c.name}] score={c.score} confidence={c.confidence:.2f}: {c.evidence_quote[:70]!r}")
    if warnings:
        print("\nWARNINGS:")
        for w in warnings:
            print(f"  ! {w}")
    else:
        print("\nOK  every competency's evidence_quote verified against the real transcript")
