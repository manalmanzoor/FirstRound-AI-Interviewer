"""Bridges the scorer's Pydantic Scorecard model to the real evidence_check
guardrail (src/guardrails/evidence_check.py), so the scorer is held to
the exact same "is this a real quote" standard as save_score in the MCP
server -- one guardrail implementation, not two independent ones that
could silently drift apart.
"""

from src.guardrails.evidence_check import check_evidence

from .schemas import Scorecard


def validate_scorecard_evidence(scorecard: Scorecard, transcript_turns: list[dict]) -> list[str]:
    warnings = []
    for c in scorecard.competencies:
        result = check_evidence(c.evidence_quote, transcript_turns)
        if not result.valid:
            warnings.append(f"{c.name}: {result.reason}")
    return warnings
