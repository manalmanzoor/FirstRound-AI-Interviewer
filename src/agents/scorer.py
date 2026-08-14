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

from .gemini import structured
from .guardrails_bridge import validate_scorecard_evidence
from .schemas import Scorecard

ROOT = Path(__file__).resolve().parents[2]

PROMPT_TEMPLATE = """You are scoring a completed technical interview. This
is the actual product of this whole system -- score honestly, not
generously.

THE SINGLE MOST IMPORTANT RULE: a confident-sounding but wrong or
hand-wavy answer must score LOWER than a hesitant but technically
correct one. Fluency and confidence are not signals of competence --
substance is. If a guardrail flag below says "possible_bluff" for a
competency, that is a strong signal that competency's score and
confidence should be LOW, regardless of how fluent the answer sounded.

For every competency you score:
- evidence_quote MUST be an exact, verbatim quote from one of the
  CANDIDATE's turns in the transcript below (not paraphrased, not from
  the agent's turns). A score whose evidence can't be found verbatim in
  the transcript will be rejected downstream.
- score is 1-5 (1=poor, 3=adequate, 5=excellent).
- confidence (0.0-1.0) reflects how confident *you* are in this specific
  score given the evidence available, not the candidate's confidence.
- reasoning should reference the specific evidence, not restate generic
  interview advice.

overall_score: a 0.0-5.0 weighted sense of the whole interview.
recommendation: one of "strong_hire", "hire", "borderline", "no_hire".
recommendation_reasoning should be specific to this candidate's actual
answers, not generic.
strengths/concerns: specific, evidence-backed, not generic platitudes.

CANDIDATE: {candidate_name}
ROLE: {role}
GUARDRAIL FLAGS FROM THE LIVE INTERVIEW (bluffs already detected,
banned questions already blocked): {guardrail_flags}
GITHUB-GROUNDED QUESTIONS ASKED: {github_grounded_questions_asked}

QUESTION PLAN (for competency/source context):
{question_plan_json}

FULL TRANSCRIPT:
{transcript_json}
"""


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
