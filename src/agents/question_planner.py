"""question_planner: jd.json + resume.json + github.json -> output/prep/question_plan.json.

Folds gap analysis in directly (compare JD requirements against resume/
GitHub evidence to decide what to probe) rather than persisting a separate
gap_analysis.json -- the PRD's repo structure (section 3) only names
jd_parser/resume_parser/github_agent/question_planner/scorer as files, not
a standalone gap_analysis module.

Requirement #4 (>=3 GitHub-grounded questions, genuinely specific) is
enforced two ways: the prompt is given real fetched repo/file/commit data
to cite (not free to invent), and _validate_github_grounding below checks
every github-sourced question's source_reference actually names a repo
that was really fetched.
"""

import json
from pathlib import Path

from .gemini import structured
from .schemas import GitHubData, JobDescription, QuestionPlan, Resume

ROOT = Path(__file__).resolve().parents[2]
MIN_GITHUB_QUESTIONS = 3

PROMPT_TEMPLATE = """You are planning questions for a live technical interview.
Compare the job description against the candidate's resume and real GitHub
activity below (a gap analysis) and produce an interview question plan.

Requirements for the plan:
- At least {min_github} questions must have source="github" and cite a
  SPECIFIC, REAL repo/file/commit from the GitHub data below in
  source_reference (e.g. "manalmanzoor/dualbook-voice-agent/booking.py" or
  "manalmanzoor/rag-chatbot commit a1b2c3d4"). Do not invent files or
  commits that aren't in the data. Ask the candidate to explain a real
  design decision, tradeoff, or piece of code from that specific
  repo/file/commit -- not a generic "tell me about this repo" question.
- Include questions with source="resume" that probe specific claims in the
  resume (source_reference = the relevant resume line/section) and
  source="jd" questions that test required qualifications the resume/
  GitHub data doesn't clearly demonstrate (this is the gap analysis --
  probe the gaps, not just what's already proven).
- Use a small, consistent set of competency names across questions (e.g.
  technical_depth, system_design, problem_solving, ai_ml_fundamentals,
  communication, ownership) so scores can be aggregated later. Don't
  invent a new competency per question.
- difficulty should be "easy", "medium", or "hard" -- start most at
  "medium", reserve "hard" for real gap-probing or deep technical
  follow-ups.
- 8-10 questions total. Set approved_by_human=false and edits_made=[]
  (a human reviewer sets these later, not you).

JOB DESCRIPTION:
{jd_json}

RESUME:
{resume_json}

GITHUB DATA (real, fetched -- only cite what's actually here):
{github_json}
"""


def _validate_github_grounding(plan: QuestionPlan, github_data: GitHubData) -> list[str]:
    """Return a list of warning strings for anything that looks ungrounded."""
    warnings = []
    known_repo_names = {r.name for r in github_data.repos} | {r.full_name for r in github_data.repos}
    github_questions = [q for q in plan.questions if q.source == "github"]

    if len(github_questions) < MIN_GITHUB_QUESTIONS:
        warnings.append(
            f"Only {len(github_questions)} github-sourced questions, need >= {MIN_GITHUB_QUESTIONS}"
        )

    for q in github_questions:
        if not any(name in q.source_reference for name in known_repo_names):
            warnings.append(f"{q.id}: source_reference '{q.source_reference}' doesn't name a real fetched repo")

    return warnings


def plan_questions(
    jd_path: Path | None = None,
    resume_path: Path | None = None,
    github_path: Path | None = None,
    output_path: Path | None = None,
) -> tuple[QuestionPlan, list[str]]:
    jd_path = jd_path or ROOT / "output" / "prep" / "jd.json"
    resume_path = resume_path or ROOT / "output" / "prep" / "resume.json"
    github_path = github_path or ROOT / "output" / "prep" / "github.json"
    output_path = output_path or ROOT / "output" / "prep" / "question_plan.json"

    jd = JobDescription.model_validate_json(jd_path.read_text(encoding="utf-8"))
    resume = Resume.model_validate_json(resume_path.read_text(encoding="utf-8"))
    github_data = GitHubData.model_validate_json(github_path.read_text(encoding="utf-8"))

    prompt = PROMPT_TEMPLATE.format(
        min_github=MIN_GITHUB_QUESTIONS,
        jd_json=jd.model_dump_json(indent=2),
        resume_json=resume.model_dump_json(indent=2),
        github_json=github_data.model_dump_json(indent=2),
    )
    plan = structured(prompt, QuestionPlan)
    warnings = _validate_github_grounding(plan, github_data)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(plan.model_dump(), indent=2), encoding="utf-8")
    return plan, warnings


if __name__ == "__main__":
    plan, warnings = plan_questions()
    by_source = {}
    for q in plan.questions:
        by_source[q.source] = by_source.get(q.source, 0) + 1
    print(f"OK  planned {len(plan.questions)} questions: {by_source}")
    for q in plan.questions:
        print(f"  [{q.source:6s}] {q.id} ({q.difficulty}): {q.text[:80]}")
        if q.source == "github":
            print(f"           -> {q.source_reference}")
    if warnings:
        print("\nWARNINGS:")
        for w in warnings:
            print(f"  ! {w}")
    else:
        print("\nOK  all github-sourced questions cite a real fetched repo")
