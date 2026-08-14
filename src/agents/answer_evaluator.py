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

from src.prompts import load_prompt

from .gemini import structured

Quality = Literal["strong", "shallow", "bluff", "off_topic", "silence"]


class AnswerEvaluation(BaseModel):
    quality: Quality
    reasoning: str


PROMPT_TEMPLATE = load_prompt("answer_evaluator")


def evaluate_answer(question: str, answer: str, competency: str) -> AnswerEvaluation:
    prompt = PROMPT_TEMPLATE.format(competency=competency, question=question, answer=answer)
    return structured(prompt, AnswerEvaluation)
