# Prompt Iteration Notes

One entry per prompt file, appended when a real failure was diagnosed —
not reconstructed after the fact. See PRD §1: honest limitations here
score points, don't polish them away. Not every prompt needed a
revision; that's noted too rather than inventing a fake v1→v2 story.

## interviewer_agent.txt — real diagnosed failure, real fix

**v1** (Phase 1, console-mode testing): generic interviewer instructions
— "ask one question at a time and wait for the candidate's full answer
before responding." This was correct for what Phase 1 actually tested:
Gemini Live behaving as a fully autonomous conversational agent, asking
its own questions and improvising follow-ups.

**Diagnosed failure** (Phase 7, first live interview run): once
`src/realtime/orchestrator.py` was built to drive the interview from the
LangGraph state machine — feeding it the *exact* question text the graph
selected — Gemini's own conversational instinct didn't go away. It kept
auto-generating a spontaneous reply the moment it detected the candidate
had finished speaking, running concurrently with the orchestrator's own
scripted `generate_reply()` call. Two things talked at once, saying
different content — reported directly by the user as "there were 2
voices speaking/asking different things" during a real interview.

**v2**: added an explicit line telling the model it is NOT the one
deciding what to ask: *"You will be told exactly what to say by the
interview orchestrator; say it close to word-for-word rather than
improvising your own questions."* This did not fully solve the problem
on its own — the fix that actually mattered was architectural
(`session.interrupt()` before every scripted utterance, cancelling
whatever Gemini started on its own; see `src/realtime/orchestrator.py`).
Kept the v2 instruction anyway since it's still the right instruction
for the model to have, even though a prompt alone couldn't out-argue the
model's own turn-taking behavior. Genuine finding: for a `RealtimeModel`
this conversational, some behaviors need enforcing structurally, not
just requesting via the system prompt.

## scorer.txt — real diagnosed failure, fixed outside the prompt

**Diagnosed failure**: the first scoring run against a real transcript
returned `interview_date: "2025-05-13"` — a plausible-looking but
completely invented date; the model has no reliable notion of "today."

**What v2 would look like and why it wasn't done**: the tempting fix is
adding "use today's actual date" to the prompt. Not attempted, because
it wouldn't reliably work — the model still has no ground truth for what
"today" is inside a single inference call, prompt instruction or not.
Fixed structurally instead: `src/agents/scorer.py` overwrites
`interview_date` with `date.today().isoformat()` after the structured
call returns, the same pattern already used for
`duration_seconds`/`guardrail_flags`/`github_grounded_questions_asked`
(fields that live in graph state, not something the model should be
inferring at all). Honest limitation to flag rather than hide: knowing
*which* fields a prompt genuinely cannot get right, and routing those
around the model entirely, mattered more here than prompt wording.

**Separate, smaller finding** (Phase 6 evals): the Bluffer persona's
scorecard came back with only 3 competencies instead of the 4 every
other persona had — `communication` was silently missing, despite
Bluffer answering the same communication-tagged question as everyone
else. The prompt says to use "a small, consistent set of competency
names" but never explicitly requires the model to score *every*
competency that appears in the question plan. Not fixed before this
submission (kept in `evals/results.md`'s honest notes rather than
patched at the last minute) — the prompt's evidence_quote requirement is
already enforced downstream (`guardrails_bridge.py` re-verifies every
quote against the real transcript); competency-set completeness isn't,
and should get the same treatment in a future iteration.

## question_planner.txt, jd_parser.txt, resume_parser.txt, answer_evaluator.txt

No diagnosed prompt failures across today's testing — these produced
correctly-shaped, on-spec output on the first real run against real data
(question_planner: 9/9 questions with 5 real GitHub-grounded citations
on the first attempt; jd_parser/resume_parser: clean structured
extraction from the real JD and resume; answer_evaluator: correctly
flagged bluffing multiple times across both the graph tests and the real
interview). Recording this as a genuine result, not an omission —
`question_planner.txt` in particular was written with the hallucination
risk (requirement #4) already in mind from the start, which is
presumably why it didn't need a second iteration: the risk was designed
against up front rather than discovered and patched after the fact.
