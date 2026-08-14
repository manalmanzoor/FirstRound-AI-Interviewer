"""Shared Gemini client for the offline reasoning pipeline (parsing,
grounding, planning, scoring, per-turn evaluation). Not used for the
realtime call -- see src/realtime/agent.py for that.
"""

import os
import re
import time

from dotenv import load_dotenv
from google import genai
from google.genai.errors import ClientError, ServerError
from pydantic import BaseModel

load_dotenv()

# gemini-2.5-flash/-flash-lite are dead on this account (Phase 0).
# gemini-3.5-flash (used through Phase 2) turned out to have only a
# 20-requests/DAY free-tier quota -- exhausted partway through Phase 3
# testing. Switched to gemini-3.1-flash-lite, which survived when 3.5-flash
# was already exhausted, implying a separate and larger quota bucket
# (exact number requires the account owner's AI Studio dashboard login,
# which isn't available here -- see ARCHITECTURE.md Phase 3). Pinned
# explicitly rather than a "-latest" alias, same reasoning as the Live
# model in Phase 0: don't let the model silently change mid-build.
OFFLINE_MODEL_ID = "gemini-3.1-flash-lite"

# Free tier is tight enough that both per-minute (429) and per-day (429
# with a different quotaId) exhaustion have been observed for real during
# testing. See ARCHITECTURE.md Phase 3.
MAX_RETRIES = 3
DEFAULT_RETRY_DELAY_S = 60

_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


class DailyQuotaExhausted(RuntimeError):
    """Raised instead of retrying when the 429 is a per-day quota, not a
    per-minute one -- waiting 60s and retrying against a daily cap just
    wastes real time, it won't reset today."""


def _is_daily_quota(error: ClientError) -> bool:
    try:
        for detail in error.details.get("error", {}).get("details", []):
            for violation in detail.get("violations", []):
                if "PerDay" in violation.get("quotaId", ""):
                    return True
    except (AttributeError, KeyError, TypeError):
        pass
    return False


def _retry_delay_s(error: ClientError) -> float:
    """Pull the server-suggested retry delay out of a 429 response if
    present, otherwise fall back to a conservative default."""
    try:
        for detail in error.details.get("error", {}).get("details", []):
            if "retryDelay" in detail:
                match = re.match(r"([\d.]+)s", detail["retryDelay"])
                if match:
                    return float(match.group(1)) + 1  # small margin
    except (AttributeError, KeyError, TypeError):
        pass
    return DEFAULT_RETRY_DELAY_S


def structured(prompt: str, schema: type[BaseModel]) -> BaseModel:
    """Call Gemini and parse the response into the given Pydantic model."""
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            response = _client.models.generate_content(
                model=OFFLINE_MODEL_ID,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": schema,
                },
            )
            return schema.model_validate_json(response.text)
        except ClientError as e:
            if e.code != 429:
                raise
            if _is_daily_quota(e):
                raise DailyQuotaExhausted(
                    f"Daily free-tier quota exhausted for {OFFLINE_MODEL_ID}. "
                    "Won't reset until tomorrow -- switch OFFLINE_MODEL_ID to a "
                    "model with remaining quota instead of retrying."
                ) from e
            if attempt == MAX_RETRIES - 1:
                raise
            delay = _retry_delay_s(e)
            print(f"  (rate limited, waiting {delay:.0f}s before retry {attempt + 1}/{MAX_RETRIES - 1})")
            last_error = e
            time.sleep(delay)
        except ServerError as e:
            # Transient "model overloaded" 503s -- observed for real in
            # Phase 3 testing, short exponential backoff (not the full
            # per-minute wait a 429 needs).
            if e.code not in (500, 503) or attempt == MAX_RETRIES - 1:
                raise
            delay = 2 ** (attempt + 1)
            print(f"  (server unavailable, waiting {delay}s before retry {attempt + 1}/{MAX_RETRIES - 1})")
            last_error = e
            time.sleep(delay)
    raise last_error
