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

from src.prompts import load_prompt

from .gemini import structured
from .schemas import GitHubData, JobDescription, QuestionPlan, Resume

ROOT = Path(__file__).resolve().parents[2]
MIN_GITHUB_QUESTIONS = 3

PROMPT_TEMPLATE = load_prompt("question_planner")


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
