"""github_agent: fetch real repo/file/commit data for a GitHub handle ->
output/prep/github.json (requirement #4 grounding material).

Deliberately fetches real file excerpts and real commit SHAs/messages, not
just repo names -- question_planner needs concrete source_reference values
("repo/file/commit"), and those have to trace back to something real here,
not something the LLM invents downstream.
"""

import base64
import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

from .schemas import GitHubCommit, GitHubData, GitHubFile, GitHubRepo

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]
API = "https://api.github.com"
MAX_REPOS = 4
MAX_FILES_PER_REPO = 2
MAX_COMMITS_PER_REPO = 5
SOURCE_EXTENSIONS = (".py", ".js", ".ts", ".tsx", ".jsx", ".dart", ".php", ".java", ".go")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github+json",
    }


def _get(path: str, params: dict | None = None, retries: int = 3) -> requests.Response:
    last_error = None
    for attempt in range(retries):
        try:
            resp = requests.get(f"{API}{path}", headers=_headers(), params=params, timeout=15)
            resp.raise_for_status()
            return resp
        except requests.exceptions.SSLError as e:
            # Transient handshake blips observed on this network -- worth a
            # couple of retries rather than failing the whole prep run.
            last_error = e
            time.sleep(1.5 * (attempt + 1))
    raise last_error


def _readme_excerpt(full_name: str, max_chars: int = 600) -> str:
    try:
        resp = _get(f"/repos/{full_name}/readme")
        content = base64.b64decode(resp.json()["content"]).decode("utf-8", errors="replace")
        return content[:max_chars]
    except requests.HTTPError:
        return ""


def _top_files(full_name: str) -> list[GitHubFile]:
    try:
        resp = _get(f"/repos/{full_name}/contents")
        entries = resp.json()
    except requests.HTTPError:
        return []

    candidates = [e for e in entries if e["type"] == "file" and e["name"].endswith(SOURCE_EXTENSIONS)]
    files: list[GitHubFile] = []
    for entry in candidates[:MAX_FILES_PER_REPO]:
        try:
            file_resp = _get(f"/repos/{full_name}/contents/{entry['path']}")
            content = base64.b64decode(file_resp.json()["content"]).decode("utf-8", errors="replace")
            files.append(GitHubFile(path=entry["path"], excerpt=content[:800]))
        except requests.HTTPError:
            continue
    return files


def _recent_commits(full_name: str) -> list[GitHubCommit]:
    try:
        resp = _get(f"/repos/{full_name}/commits", params={"per_page": MAX_COMMITS_PER_REPO})
    except requests.HTTPError:
        return []
    return [
        GitHubCommit(
            sha=c["sha"][:8],
            message=c["commit"]["message"].splitlines()[0],
            date=c["commit"]["author"]["date"],
        )
        for c in resp.json()
    ]


def fetch_github_data(username: str, output_path: Path | None = None) -> GitHubData:
    output_path = output_path or ROOT / "output" / "prep" / "github.json"

    profile = _get(f"/users/{username}").json()

    repos_resp = _get(
        f"/users/{username}/repos",
        params={"sort": "pushed", "direction": "desc", "per_page": 20},
    ).json()
    non_forks = [r for r in repos_resp if not r["fork"]]
    top_repos = (non_forks or repos_resp)[:MAX_REPOS]

    repos = [
        GitHubRepo(
            name=r["name"],
            full_name=r["full_name"],
            description=r["description"] or "",
            language=r["language"] or "",
            url=r["html_url"],
            readme_excerpt=_readme_excerpt(r["full_name"]),
            top_files=_top_files(r["full_name"]),
            recent_commits=_recent_commits(r["full_name"]),
        )
        for r in top_repos
    ]

    result = GitHubData(
        username=username,
        name=profile.get("name") or username,
        bio=profile.get("bio") or "",
        public_repos=profile.get("public_repos", 0),
        repos=repos,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result.model_dump(), indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    import sys

    handle = sys.argv[1] if len(sys.argv) > 1 else "manalmanzoor"
    data = fetch_github_data(handle)
    total_files = sum(len(r.top_files) for r in data.repos)
    total_commits = sum(len(r.recent_commits) for r in data.repos)
    print(f"OK  fetched {len(data.repos)} repos, {total_files} file excerpts, "
          f"{total_commits} commits for '{handle}'")
    for r in data.repos:
        print(f"  - {r.name} ({r.language}): {len(r.top_files)} files, {len(r.recent_commits)} commits")
