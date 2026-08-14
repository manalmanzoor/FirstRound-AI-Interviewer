"""parse_resume: inputs/resume.pdf -> output/prep/resume.json (requirement #3).

Zero manual field entry: pdfplumber extracts raw text, Gemini structured
output does the rest. No hardcoded assumptions about resume layout, since
"survives a messy PDF" is part of the acceptance test.
"""

import json
from pathlib import Path

import pdfplumber

from .gemini import structured
from .schemas import Resume

ROOT = Path(__file__).resolve().parents[2]

PROMPT_TEMPLATE = """Extract structured fields from this resume text
(raw-extracted from a PDF, so spacing/line breaks may be imperfect).
Be faithful to the source -- do not invent experience, projects, or
skills that aren't present. github_handle should be just the username
(no URL, no "github.com/" prefix). If a field genuinely isn't present,
use an empty string or empty list.

RESUME TEXT:
{resume_text}
"""


def extract_pdf_text(pdf_path: Path) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    text = "\n\n".join(pages)
    if not text.strip():
        raise ValueError(f"No extractable text in {pdf_path} -- likely a scanned/image-only PDF")
    return text


def parse_resume(input_path: Path | None = None, output_path: Path | None = None) -> Resume:
    input_path = input_path or ROOT / "inputs" / "resume.pdf"
    output_path = output_path or ROOT / "output" / "prep" / "resume.json"

    resume_text = extract_pdf_text(input_path)
    result = structured(PROMPT_TEMPLATE.format(resume_text=resume_text), Resume)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result.model_dump(), indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    resume = parse_resume()
    print(f"OK  parsed resume: {resume.name} (github: {resume.github_handle}), "
          f"{len(resume.experience)} experience entries, {len(resume.projects)} projects")
