# Eval Results

5 synthetic personas, all answering the SAME real question plan (output/prep/question_plan.json, generated from the real resume + GitHub data in earlier phases), scored by the real scorer (src/agents/scorer.py) -- not a mock or simplified path.

**Expected ranking:** strong > nervous > average > bluffer > weak
**Actual ranking:** strong > nervous > average > bluffer > weak
**Ranking matches expected order exactly:** YES
**The real test -- bluffer scored below nervous:** YES

## Scores

| Persona | Overall Score | Recommendation | Guardrail Flags |
|---|---|---|---|
| strong | 4.30 | strong_hire | 0 |
| nervous | 3.00 | hire | 0 |
| average | 2.00 | no_hire | 0 |
| bluffer | 1.00 | no_hire | 2 |
| weak | 1.00 | no_hire | 0 |

## Per-competency breakdown

### strong

| Competency | Score | Confidence |
|---|---|---|
| system_design | 4 | 0.90 |
| technical_depth | 5 | 0.95 |
| problem_solving | 4 | 0.85 |
| communication | 4 | 0.90 |

**Recommendation reasoning:** Manal demonstrates excellent technical clarity, specifically in RAG pipeline design, asynchronous pattern usage, and production-grade system design. She articulates trade-offs well and shows a deep understanding of the practical challenges in building reliable AI systems.

### nervous

| Competency | Score | Confidence |
|---|---|---|
| system_design | 3 | 0.80 |
| technical_depth | 3 | 0.70 |
| problem_solving | 3 | 0.80 |
| communication | 3 | 0.90 |

**Recommendation reasoning:** Manal demonstrates a solid foundational understanding of AI engineering tasks, including thread management, state machine design, and evaluation logic. While she lacks deep production-grade experience with FastAPI and advanced orchestration frameworks, her answers are grounded in real implementation attempts and she possesses the technical self-awareness to recognize the limitations of her previous approaches.

### average

| Competency | Score | Confidence |
|---|---|---|
| system_design | 2 | 0.90 |
| technical_depth | 2 | 0.85 |
| problem_solving | 2 | 0.90 |
| communication | 3 | 0.95 |

**Recommendation reasoning:** While the candidate presents themselves as an AI engineer, the technical depth demonstrated in the interview was consistently shallow. They rely on high-level concepts and lack the rigor required for production-grade engineering at Northwind Labs. Answers to specific questions regarding architecture, testing, and concurrency were surface-level and lacked necessary implementation detail.

### bluffer

| Competency | Score | Confidence |
|---|---|---|
| system_design | 1 | 0.95 |
| technical_depth | 1 | 0.95 |
| problem_solving | 1 | 0.90 |

**Recommendation reasoning:** The candidate consistently responded to technical questions with generic, confident-sounding platitudes that lacked substance. They demonstrated a pattern of bluffing on technical implementation details (as flagged in the guardrails) and displayed a lack of humility or technical curiosity expected in a Junior AI Engineer. There was no evidence of actual engineering depth or ability to articulate trade-offs in systems design.

### weak

| Competency | Score | Confidence |
|---|---|---|
| system_design | 1 | 0.95 |
| technical_depth | 1 | 0.95 |
| problem_solving | 1 | 0.95 |
| communication | 2 | 0.80 |

**Recommendation reasoning:** The candidate could not explain the architecture, design choices, or technical implementation details of their own projects listed on their resume and GitHub. They demonstrated a lack of fundamental knowledge in Python, FastAPI, and system design, and admitted to having no experience in evaluation systems, which is a critical requirement for this position.

## Honest notes

Ranking came out exactly as expected on this run. Worth being skeptical of a clean result: 5 personas is a small sample, the answers were hand-written by the same person who wrote the scoring prompt (some risk of the prompt being tuned, even unconsciously, to the personas rather than the other way around), and LLM-based scoring has run-to-run variance that wasn't tested here (single run per persona, not repeated).

Two things in the raw output that are NOT clean and are reported as-is rather than smoothed over:

- **Bluffer and Weak tied at exactly 1.00 overall.** The core requirement (bluffer < nervous) held, but bluffer and weak are meant to be distinguishable failure modes -- a confident bluffer and someone who honestly says "I don't know" are different problems for a hiring team, and a real scorecard collapsing them to the identical score loses that distinction. Likely cause: with every competency floored at score=1, there's no room left in a 1-5 scale to separate "actively misleading" from "honestly out of their depth" -- worth a half-point penalty or separate flag for detected bluffing in a future iteration, rather than only lowering the same 1-5 score bluffing would already floor.
- **Bluffer's scorecard has only 3 competencies (system_design, technical_depth, problem_solving); every other persona has all 4, including communication.** All 5 personas answered the same 9 questions, including the communication-tagged one (q9), so this wasn't a case of the question never being asked. The model chose not to emit a communication entry for Bluffer rather than scoring it low -- an omission the prompt's schema doesn't currently forbid. Worth tightening the prompt (or validating competency-set completeness downstream, the same way evidence_quote is already validated) so a competency can't silently disappear instead of being scored.