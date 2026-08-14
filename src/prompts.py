"""Loads system prompts from prompts/*.txt (requirement #12: every system
prompt is its own file, not a string buried in code)."""

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8")
