"""Requirement #9: both guardrails need "a test file proving each fires,
not just a code comment claiming they do" (PRD section 8). This is that
test file, for both guardrails.

Run: python -m src.guardrails_test
"""

from src.guardrails.banned_questions import check_question
from src.guardrails.evidence_check import check_evidence


def test_banned_questions_blocks_each_category():
    cases = [
        ("How old are you?", "age"),
        ("Are you male or female?", "gender"),
        ("What's your marital status?", "marital_status"),
        ("Are you planning to have children soon?", "marital_status"),
        ("What religion do you practice?", "religion"),
        ("What's your immigration status?", "nationality"),
        ("Are you currently pregnant?", "health_pregnancy"),
        ("What was your salary at your last job?", "salary_history"),
        ("Who did you vote for in the last election?", "politics"),
    ]
    for question, expected_topic in cases:
        result = check_question(question)
        assert result.blocked, f"expected {question!r} to be blocked, but it wasn't"
        assert result.topic == expected_topic, f"{question!r} blocked for {result.topic!r}, expected {expected_topic!r}"
    print(f"OK  banned_questions blocked all {len(cases)} banned-topic categories")


def test_banned_questions_allows_legitimate_technical_questions():
    cases = [
        "Walk me through your commit history on the RAG-RedTeam-Toolkit repo.",
        "How did you handle thread safety in your background job runner?",
        "What tradeoffs did you consider between LangGraph and a custom state machine?",
        "How old is the oldest dependency in your requirements.txt?",  # "old" but not about candidate's age
    ]
    for question in cases:
        result = check_question(question)
        assert not result.blocked, f"expected {question!r} to be allowed, but it was blocked for {result.topic!r}"
    print(f"OK  banned_questions did not false-positive on {len(cases)} legitimate technical questions")


def test_evidence_check_rejects_empty_quote():
    transcript = [{"speaker": "candidate", "text": "I used a threading.Lock to guard job state."}]
    result = check_evidence("", transcript)
    assert not result.valid
    result = check_evidence("   ", transcript)
    assert not result.valid
    print("OK  evidence_check rejects empty/whitespace-only evidence_quote")


def test_evidence_check_rejects_fabricated_quote():
    transcript = [{"speaker": "candidate", "text": "I used a threading.Lock to guard job state."}]
    result = check_evidence("I wrote extensive unit tests for every edge case", transcript)
    assert not result.valid, "a quote that never appears in the transcript should be rejected"
    print(f"OK  evidence_check rejects a fabricated quote not present in transcript: {result.reason!r}")


def test_evidence_check_accepts_real_quote():
    transcript = [
        {"speaker": "agent", "text": "How did you handle concurrent access?"},
        {"speaker": "candidate", "text": "I used a threading.Lock to guard job state."},
    ]
    result = check_evidence("I used a threading.Lock to guard job state.", transcript)
    assert result.valid, f"a real transcript quote should be accepted, got: {result.reason}"
    print("OK  evidence_check accepts a real quote found in a candidate transcript turn")


def test_evidence_check_ignores_agent_turns():
    """A quote must come from the CANDIDATE, not something the agent said."""
    transcript = [{"speaker": "agent", "text": "That sounds like a solid approach to concurrency."}]
    result = check_evidence("That sounds like a solid approach to concurrency.", transcript)
    assert not result.valid, "a quote from the agent's own turn should not count as candidate evidence"
    print("OK  evidence_check does not accept a quote sourced from the agent's own turn")


if __name__ == "__main__":
    test_banned_questions_blocks_each_category()
    test_banned_questions_allows_legitimate_technical_questions()
    test_evidence_check_rejects_empty_quote()
    test_evidence_check_rejects_fabricated_quote()
    test_evidence_check_accepts_real_quote()
    test_evidence_check_ignores_agent_turns()
    print("\nOK  both guardrails proven to fire correctly, with no false positives on legitimate content")
