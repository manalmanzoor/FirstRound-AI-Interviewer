"""Guardrail #9b: no score without a transcript quote, enforced at the
scoring node (PRD section 8) -- and enforced as a real quote from the
transcript, not just any non-empty string. A hallucinated-but-plausible
"evidence quote" that never appears in the conversation would defeat the
entire point of the requirement, so this checks the quote actually
occurs in a candidate transcript turn, not just that the field is filled
in. mcp_server/server.py's save_score uses this same function, so the
MCP tool and the scorer enforce identically.
"""

import re
from dataclasses import dataclass


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


@dataclass
class EvidenceCheckResult:
    valid: bool
    reason: str | None = None


def check_evidence(evidence_quote: str, transcript: list[dict]) -> EvidenceCheckResult:
    if not evidence_quote or not evidence_quote.strip():
        return EvidenceCheckResult(valid=False, reason="evidence_quote is empty")

    normalized_quote = _normalize(evidence_quote)
    candidate_turns = [_normalize(t["text"]) for t in transcript if t.get("speaker") == "candidate"]

    if any(normalized_quote in turn for turn in candidate_turns):
        return EvidenceCheckResult(valid=True)

    return EvidenceCheckResult(
        valid=False,
        reason="evidence_quote does not appear in any candidate transcript turn -- looks fabricated",
    )
