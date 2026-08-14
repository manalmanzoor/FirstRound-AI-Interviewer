"""Lightweight per-turn evaluator: judges one candidate answer against the
question that prompted it. Shared by the graph's adaptive-follow-up
routing (requirement #6) and, per PRD section 11, the same evaluator
should back any live scoreboard later -- one pipeline, not two.

This is intentionally NOT the final scorer (src/agents/scorer.py, built in
a later phase) -- that one produces the full scorecard.json with
evidence quotes after the interview. This one just needs to be fast
enough to drive routing decisions turn-by-turn during the live call.
"""

from typing import Literal

from pydantic import BaseModel

from .gemini import structured

Quality = Literal["strong", "shallow", "bluff", "off_topic", "silence"]


class AnswerEvaluation(BaseModel):
    quality: Quality
    reasoning: str


PROMPT_TEMPLATE = """You are silently judging one answer in a live technical
interview, to decide how to route the conversation next. Be decisive --
this drives real-time follow-up logic, not a final grade.

QUESTION ({competency}): {question}

CANDIDATE'S ANSWER: {answer}

Classify the answer as exactly one of:
- "strong": specific, technically sound, demonstrates real understanding
- "shallow": vague, surface-level, avoids specifics that the question asked for
- "bluff": confident-sounding but the specifics don't add up, contradicts
  known facts about their own project, or hand-waves through details a
  person who actually did the work would know
- "off_topic": doesn't address the question asked
- "silence": no real answer given (empty, "I don't know", trails off)
"""


def evaluate_answer(question: str, answer: str, competency: str) -> AnswerEvaluation:
    prompt = PROMPT_TEMPLATE.format(competency=competency, question=question, answer=answer)
    return structured(prompt, AnswerEvaluation)
