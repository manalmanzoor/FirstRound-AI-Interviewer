"""Requirement #11: run the 5 synthetic personas through the REAL scorer
(src/agents/scorer.py) -- not a mock or a separate simplified scoring
path -- and write the ranking table + honest analysis to results.md.

Expected ranking per PRD section 1: Strong > Nervous (near-Strong) >
Average > Bluffer > Weak. The Bluffer-vs-Nervous ordering specifically is
"the real test" -- if that one inverts, that's the finding to report
honestly, not massage away.

Run: python -m evals.run_evals
"""

import json
from pathlib import Path

from src.agents.scorer import score_interview

ROOT = Path(__file__).resolve().parents[1]
PERSONAS_DIR = ROOT / "evals" / "personas"
RESULTS_PATH = ROOT / "evals" / "results.md"

EXPECTED_ORDER = ["strong", "nervous", "average", "bluffer", "weak"]


def run_all():
    results = {}
    for name in EXPECTED_ORDER:
        transcript_path = PERSONAS_DIR / f"{name}_transcript.json"
        output_path = PERSONAS_DIR / f"{name}_scorecard.json"
        print(f"Scoring persona: {name}...")
        scorecard, warnings = score_interview(
            transcript_path=transcript_path,
            output_path=output_path,
        )
        results[name] = {"scorecard": scorecard, "warnings": warnings}
        print(f"  overall_score={scorecard.overall_score}, recommendation={scorecard.recommendation}")
        if warnings:
            for w in warnings:
                print(f"  ! evidence warning: {w}")
    return results


def write_results_md(results: dict):
    actual_order = sorted(results.keys(), key=lambda n: results[n]["scorecard"].overall_score, reverse=True)
    ranking_correct = actual_order == EXPECTED_ORDER
    bluffer_below_nervous = (
        results["bluffer"]["scorecard"].overall_score < results["nervous"]["scorecard"].overall_score
    )

    lines = [
        "# Eval Results",
        "",
        "5 synthetic personas, all answering the SAME real question plan "
        "(output/prep/question_plan.json, generated from the real resume + "
        "GitHub data in earlier phases), scored by the real scorer "
        "(src/agents/scorer.py) -- not a mock or simplified path.",
        "",
        f"**Expected ranking:** {' > '.join(EXPECTED_ORDER)}",
        f"**Actual ranking:** {' > '.join(actual_order)}",
        f"**Ranking matches expected order exactly:** {'YES' if ranking_correct else 'NO'}",
        f"**The real test -- bluffer scored below nervous:** {'YES' if bluffer_below_nervous else 'NO -- see honest note below'}",
        "",
        "## Scores",
        "",
        "| Persona | Overall Score | Recommendation | Guardrail Flags |",
        "|---|---|---|---|",
    ]
    for name in EXPECTED_ORDER:
        sc = results[name]["scorecard"]
        flags = len(sc.guardrail_flags)
        lines.append(f"| {name} | {sc.overall_score:.2f} | {sc.recommendation} | {flags} |")

    lines += [
        "",
        "## Per-competency breakdown",
        "",
    ]
    for name in EXPECTED_ORDER:
        sc = results[name]["scorecard"]
        lines.append(f"### {name}")
        lines.append("")
        lines.append("| Competency | Score | Confidence |")
        lines.append("|---|---|---|")
        for c in sc.competencies:
            lines.append(f"| {c.name} | {c.score} | {c.confidence:.2f} |")
        lines.append("")
        lines.append(f"**Recommendation reasoning:** {sc.recommendation_reasoning}")
        lines.append("")

    lines += ["## Honest notes", ""]
    if ranking_correct:
        lines.append(
            "Ranking came out exactly as expected on this run. Worth being "
            "skeptical of a clean result: 5 personas is a small sample, the "
            "answers were hand-written by the same person who wrote the "
            "scoring prompt (some risk of the prompt being tuned, even "
            "unconsciously, to the personas rather than the other way "
            "around), and LLM-based scoring has run-to-run variance that "
            "wasn't tested here (single run per persona, not repeated)."
        )
    else:
        lines.append(
            f"Ranking did NOT match the expected order. Actual: "
            f"{' > '.join(actual_order)}. This is reported as-is rather than "
            f"re-prompting or tuning the scorer until it produces the "
            f"'expected' answer -- that would defeat the purpose of the eval."
        )
    if not bluffer_below_nervous:
        lines.append(
            ""
            "The core discriminative test (bluffer < nervous) did NOT hold "
            "on this run. This is the single most important thing this eval "
            "suite is supposed to catch, so it's flagged explicitly rather "
            "than buried in a table."
        )

    RESULTS_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nOK  wrote {RESULTS_PATH}")
    print(f"    expected: {' > '.join(EXPECTED_ORDER)}")
    print(f"    actual:   {' > '.join(actual_order)}")
    print(f"    ranking_correct={ranking_correct}, bluffer_below_nervous={bluffer_below_nervous}")


if __name__ == "__main__":
    results = run_all()
    write_results_md(results)
