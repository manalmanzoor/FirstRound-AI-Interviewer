"""parse_jd: inputs/jd.txt -> output/prep/jd.json (requirement #3)."""

import json
from pathlib import Path

from src.prompts import load_prompt

from .gemini import structured
from .schemas import JobDescription

ROOT = Path(__file__).resolve().parents[2]

PROMPT_TEMPLATE = load_prompt("jd_parser")


def parse_jd(input_path: Path | None = None, output_path: Path | None = None) -> JobDescription:
    input_path = input_path or ROOT / "inputs" / "jd.txt"
    output_path = output_path or ROOT / "output" / "prep" / "jd.json"

    jd_text = input_path.read_text(encoding="utf-8")
    result = structured(PROMPT_TEMPLATE.format(jd_text=jd_text), JobDescription)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result.model_dump(), indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    jd = parse_jd()
    print(f"OK  parsed JD: {jd.title} @ {jd.company} ({len(jd.responsibilities)} responsibilities, "
          f"{len(jd.required_qualifications)} required quals)")
