"""Generates the 5 synthetic persona transcripts (requirement #11) as
real transcript.json-shaped files, all answering the SAME real question
plan (output/prep/question_plan.json) so the comparison across personas
is apples-to-apples, not 5 different question sets.

The real test (PRD section 1) is BLUFFER vs NERVOUS: a confident-sounding
but hand-wavy/inconsistent answer must score below a hesitant-but-correct
one. Nervous's answers are deliberately written to be *more* technically
correct and specific than Bluffer's, despite reading less polished.

Run: python -m evals.personas.generate_personas
"""

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QUESTION_PLAN_PATH = ROOT / "output" / "prep" / "question_plan.json"
PERSONAS_DIR = ROOT / "evals" / "personas"

# id -> answer text, per persona. Every persona answers all 9 real
# questions so scores are comparable. Content is hand-written to be
# genuinely differentiated on substance, not just tone -- Strong and
# Nervous should both hold up under scrutiny; Bluffer should not.

STRONG = {
    "q1": "I used a threading.Lock around the shared jobs dict so only one thread mutates state at a time, and _prune_jobs runs on a timer thread that walks the dict and evicts anything older than a TTL, holding the lock only for the eviction itself, not the whole scan. In production I'd move this to Redis with a TTL-based expiry instead of an in-process dict, since a single Flask process's memory isn't shared across workers or survives a restart.",
    "q2": "Honestly, Express was just faster to prototype against the mobile client's existing Node tooling, not a technical requirement. To refactor to FastAPI I'd swap the Express routes for APIRouter endpoints, replace the Gemini client init with a dependency-injected singleton via Depends(), and use httpx.AsyncClient for the weather API calls so they don't block the event loop.",
    "q3": "The five layers were: input sanitization (strip prompt injection patterns), a retrieval-time relevance filter, an output toxicity classifier, a citation-grounding check that rejects ungrounded claims, and a final rate-limiter for abuse patterns. Latency added about 180ms end to end, mostly from the toxicity classifier call, which I mitigated by running it in parallel with generation instead of after it.",
    "q4": "The voice channel and the dashboard both write to the same SQLite-backed session store keyed by phone number, and the dashboard polls it every 2 seconds rather than holding a live socket, since booking state changes are infrequent enough that polling is simpler and avoids a whole websocket reconnection-handling surface for a first version.",
    "q5": "Playwright's page.wait_for_selector with a timeout wrapped in a retry loop handled most timing issues, and I added a fallback that re-queries by partial text match if the primary selector's structure changed, since business listing sites redesign fairly often. Failed scrapes get logged with the URL and get retried once on the next run rather than blocking the batch.",
    "q6": "I wrote a custom state machine rather than LangGraph for that one, mainly because at the time I needed fine-grained control over partial-failure recovery that I wasn't confident I could express cleanly in LangGraph's node model yet. The tradeoff was more boilerplate for state transitions, but I had full control over exactly when to persist checkpoints.",
    "q7": "I've built FastAPI endpoints using SQLAlchemy's async session with a Depends()-injected session-per-request pattern, and dependency injection for things like the current user and rate limiter. The main gotcha is making sure the session is closed even on exceptions, which I handle with a try/finally in the dependency generator function.",
    "q8": "I'd hold out a fixed test set with known-correct answers, measure retrieval precision/recall separately from generation quality, and use a rubric-based LLM judge rather than a single overall score, since a single score hides which component actually failed. To reduce judge bias I'd have the judge model be different from the generation model, and spot-check a sample against human labels periodically.",
    "q9": "Every API response includes a confidence field computed from retrieval similarity scores plus a source list with document IDs and offsets, so the frontend can render inline citations and gray out low-confidence claims without needing a second round-trip.",
}

NERVOUS = {
    "q1": "Um, sorry, let me think about this properly -- so, the jobs dict is shared across the request thread and the background thread, so I put a lock around any write to it. _prune_jobs runs periodically and just... it removes entries past a TTL. I know holding the lock for the whole scan would block new jobs from being added, so I only lock the actual delete, not the iteration. I'm not totally sure that's the most elegant way to do it, but that's the reasoning.",
    "q2": "Honestly, um, it was Express because that's what I was more comfortable with at the time, not a big technical decision. If I redid it in FastAPI I think I'd... use an async route, and replace the Gemini call with an async client so it doesn't block. I'd have to double check the exact syntax but that's the idea.",
    "q3": "Okay so there were five layers -- sorry, I want to make sure I get this right -- input filtering for injection attempts, then a retrieval relevance check, then I think a toxicity check on the output, then a grounding check to make sure the answer actually matches the retrieved sources, and a rate limiter at the end. The latency, I don't remember the exact number, but it was noticeably slower, maybe 150-200ms extra, and the toxicity check was the biggest chunk of that.",
    "q4": "So, um, the voice side and the dashboard both read and write to the same session store -- I used SQLite for it -- keyed by the phone number. The dashboard doesn't have a live connection, it just polls every couple seconds, which I know isn't ideal but I didn't think the booking state changes fast enough to need a websocket.",
    "q5": "Playwright kept timing out on slow-loading pages, so I wrapped the selector waits in a retry with a timeout, and if the page structure changed I'd fall back to searching by text instead of the exact selector. I'm not 100% sure I handled every edge case, some scrapes probably still failed silently, but the retry logic caught most of it.",
    "q6": "I didn't use LangGraph for that one -- I wrote a custom state machine, mostly because I wasn't confident I could get the failure-recovery behavior right in LangGraph at the time. It meant more code to maintain state transitions myself, but I felt like I understood exactly what was happening at each step.",
    "q7": "Um, yes, so with FastAPI and SQLAlchemy I used the async session pattern with Depends() to inject a session per request. The tricky part honestly was making sure the session actually got closed if something threw an exception partway through -- I used a try/finally for that.",
    "q8": "I'd want a held-out test set with known correct answers so I'm not just checking against the same data I built the system with. I'd measure retrieval and generation separately, since if I only look at the final answer I can't tell which part broke. For the judge bias thing, I think using a different model as the judge than the one generating answers helps some, and I'd want to spot check with real human review too, I don't fully trust an LLM judge alone.",
    "q9": "Each response has a confidence number and a list of sources with where in the document they came from, so the frontend can show citations without a second request. I think that's the main mechanism -- I might be missing something about how we'd stream it though.",
}

AVERAGE = {
    "q1": "I used a lock to make sure only one thread updates the jobs dictionary at a time. _prune_jobs cleans up old entries so memory doesn't keep growing. In production I'd probably want something more robust than an in-memory dict, like a database.",
    "q2": "I used Express because I built the mobile backend in Node already. To move it to FastAPI I'd rewrite the routes in Python and use an async client for the API calls.",
    "q3": "There were five layers for security -- checking the input, checking what gets retrieved, checking the output for bad content, making sure the answer matches the sources, and rate limiting. It did add some latency but I didn't measure it precisely.",
    "q4": "The voice part and the dashboard both use the same database to store booking info, so the dashboard just reads from there periodically to show updates.",
    "q5": "I added retries for when Playwright couldn't find elements right away, and some fallback logic for when pages looked different than expected. It mostly worked but I'm sure some edge cases slipped through.",
    "q6": "I wrote my own state machine instead of using an existing framework. It took more work but I understood how it functioned.",
    "q7": "I've used FastAPI with SQLAlchemy's async sessions before, injecting the session as a dependency for each request.",
    "q8": "I'd test against known answers, look at both retrieval and generation quality separately, and try to avoid relying only on the LLM's own judgment of itself.",
    "q9": "The backend sends a confidence score and source info along with each response so the frontend can show that to the user.",
}

BLUFFER = {
    "q1": "Oh yeah, thread safety was totally handled -- I built a really robust concurrent architecture there, it's basically enterprise-grade. _prune_jobs just cleans things up automatically, I didn't really need to think about it much, it just works. Honestly the whole thing was pretty straightforward to build, maybe a day's work.",
    "q2": "Express is just objectively better for this kind of real-time stuff, way faster than FastAPI honestly. I don't think I'd even bother switching it, Python's async story isn't as mature as Node's for this use case.",
    "q3": "Yeah the five-layer guardrail stack, that was a big deal, took real engineering. It's got input checks, output checks, like a full pipeline basically. Zero false positives in testing, it's genuinely bulletproof. Latency wasn't really an issue, it's all pretty optimized under the hood.",
    "q4": "State sync between the voice and dashboard sides was actually the hardest part of the whole project but I nailed it with a pretty clever architecture -- everything's just synced in real time, no real lag or issues there at all.",
    "q5": "Playwright reliability wasn't really a problem for me, I just wrote solid selectors and it worked fine. I didn't run into the flakiness people usually complain about with it, my scraping logic is pretty bulletproof.",
    "q6": "I used a custom framework I basically designed myself, way more powerful than LangGraph honestly, gave me full control over everything. It's a pretty sophisticated piece of engineering if I'm being honest.",
    "q7": "Oh for sure, I've built tons of complex FastAPI endpoints, async everything, dependency injection, all of it. It's second nature to me at this point, I don't even think about it.",
    "q8": "Evaluation is honestly not that complicated, you just need good test cases and a solid rubric, I could set that up pretty quickly. LLM-as-judge bias isn't really a huge concern if your prompts are well-written.",
    "q9": "Yeah the confidence signaling stuff was straightforward, I just exposed whatever metadata made sense on the backend and the frontend handled displaying it. It's a pretty standard pattern honestly.",
}

WEAK = {
    "q1": "I'm not totally sure, I think I just used a normal dictionary. I don't remember exactly how the cleanup part works, sorry.",
    "q2": "I just used what I knew at the time I guess. I haven't really used FastAPI enough to say how I'd change it.",
    "q3": "I don't remember the specifics of each layer honestly, it's been a while since I looked at that code.",
    "q4": "I think they both just talk to the same database? I'm not sure about the details of how it's synced.",
    "q5": "Yeah it broke sometimes and I'd just rerun it. I didn't build anything fancy for handling errors.",
    "q6": "I'm not sure I fully remember why I made that choice, it might have just been what I was comfortable with.",
    "q7": "I've used FastAPI a little bit but I don't remember the specifics of async sessions, sorry.",
    "q8": "I'm not really sure how I'd design that, I haven't done much with evaluation systems before.",
    "q9": "I think we just sent some extra data back but I don't remember exactly what.",
}

PERSONAS = {
    "strong": STRONG,
    "nervous": NERVOUS,
    "average": AVERAGE,
    "bluffer": BLUFFER,
    "weak": WEAK,
}


def build_transcript(persona_name: str, answers: dict[str, str], questions: list[dict]) -> dict:
    turns = []
    ts = 0
    for q in questions:
        turns.append({"speaker": "agent", "text": q["text"], "timestamp_ms": ts, "node": q["source"] + "_probe", "interrupted": False})
        ts += 15000
        turns.append({"speaker": "candidate", "text": answers[q["id"]], "timestamp_ms": ts, "node": q["source"] + "_probe", "interrupted": False})
        ts += 20000

    # Mirrors what the live graph's bluff-detection guardrail would
    # plausibly have flagged in real time for this persona (see
    # src/nodes/_content_node.py) -- these synthetic transcripts skip the
    # live interview, so this is asserted rather than actually detected.
    guardrail_flags = []
    if persona_name == "bluffer":
        guardrail_flags = [
            "possible_bluff:q1:claims robust concurrent architecture but gives no concrete mechanism",
            "possible_bluff:q3:claims zero false positives with no evaluation methodology described",
        ]

    return {
        "turns": turns,
        "guardrail_flags": guardrail_flags,
        "github_grounded_questions_asked": sum(1 for q in questions if q["source"] == "github"),
        "duration_seconds": ts // 1000,
    }


def main():
    plan = json.loads(QUESTION_PLAN_PATH.read_text(encoding="utf-8"))
    questions = plan["questions"]

    PERSONAS_DIR.mkdir(parents=True, exist_ok=True)
    for name, answers in PERSONAS.items():
        missing = [q["id"] for q in questions if q["id"] not in answers]
        if missing:
            raise ValueError(f"persona {name!r} is missing answers for: {missing}")
        transcript = build_transcript(name, answers, questions)
        out_path = PERSONAS_DIR / f"{name}_transcript.json"
        out_path.write_text(json.dumps(transcript, indent=2), encoding="utf-8")
        print(f"OK  wrote {out_path} ({len(transcript['turns'])} turns)")


if __name__ == "__main__":
    main()
