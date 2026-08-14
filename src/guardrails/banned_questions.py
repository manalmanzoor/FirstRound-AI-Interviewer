"""Guardrail #9a: banned-topic blocklist, checked BEFORE a question
reaches the candidate (PRD section 8). Keyword/pattern based rather than
an LLM call -- a "blocklist" should be deterministic and fast enough to
run on every single question without adding latency or cost to the live
call, and a test "proving it fires" is far more reliable against a
deterministic check than a stochastic model call.
"""

import re
from dataclasses import dataclass

# Each pattern is checked case-insensitively against the full question
# text. Patterns are intentionally somewhat broad (a false positive just
# means a question gets skipped/regenerated -- cheap; a false negative
# means a banned-topic question reaches the candidate -- not cheap).
BANNED_TOPICS: dict[str, list[str]] = {
    "age": [r"\bhow old are you\b", r"\byour age\b", r"\bwhat.?s your age\b", r"\bbirth ?year\b", r"\bdate of birth\b"],
    "gender": [r"\byour gender\b", r"\bare you (a man|a woman|male|female|non-binary)\b", r"\bpreferred pronouns\b"],
    "marital_status": [r"\bare you married\b", r"\bmarital status\b", r"\bdo you have (a )?(spouse|husband|wife)\b", r"\bplan(s|ning)? to (get married|have (a )?kids?|have children)\b"],
    "religion": [r"\byour religion\b", r"\bwhat religion\b", r"\bare you (religious|muslim|christian|hindu|jewish|atheist)\b", r"\bwhich faith\b"],
    "nationality": [r"\byour nationality\b", r"\bwhere (were you born|are you from originally)\b", r"\bimmigration status\b", r"\bvisa status\b", r"\bare you a citizen\b"],
    "health_pregnancy": [r"\bare you (currently |now |already )?pregnant\b", r"\bplan(s|ning)? (to get|of getting) pregnant\b", r"\byour health condition\b", r"\bdo you have (a )?disabilit(y|ies)\b", r"\bmedical (condition|history)\b"],
    "salary_history": [r"\byour salary\b", r"\bhow much (were|are) you (paid|making)\b", r"\bsalary history\b", r"\byour (current|last) (pay|compensation)\b"],
    "politics": [r"\bwho did you vote for\b", r"\byour political (views|affiliation|party)\b", r"\bare you (a )?(republican|democrat|conservative|liberal)\b"],
}

_COMPILED = {topic: [re.compile(p, re.IGNORECASE) for p in patterns] for topic, patterns in BANNED_TOPICS.items()}


@dataclass
class BannedTopicResult:
    blocked: bool
    topic: str | None = None
    matched_pattern: str | None = None


def check_question(text: str) -> BannedTopicResult:
    for topic, patterns in _COMPILED.items():
        for pattern in patterns:
            if pattern.search(text):
                return BannedTopicResult(blocked=True, topic=topic, matched_pattern=pattern.pattern)
    return BannedTopicResult(blocked=False)
