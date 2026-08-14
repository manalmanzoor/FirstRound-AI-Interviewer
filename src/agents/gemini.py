"""Shared Gemini client for the offline reasoning pipeline (parsing,
grounding, planning, scoring). Not used for the realtime call -- see
src/realtime/agent.py for that.
"""

import os

from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel

load_dotenv()

# Confirmed working in Phase 0 -- see ARCHITECTURE.md. gemini-2.5-flash/
# -flash-lite are both dead ("no longer available to new users") on this
# account despite still showing up in models.list().
OFFLINE_MODEL_ID = "gemini-3.5-flash"

_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def structured(prompt: str, schema: type[BaseModel]) -> BaseModel:
    """Call Gemini and parse the response into the given Pydantic model."""
    response = _client.models.generate_content(
        model=OFFLINE_MODEL_ID,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": schema,
        },
    )
    return schema.model_validate_json(response.text)
