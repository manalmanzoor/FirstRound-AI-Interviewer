"""Pydantic models for the prep pipeline. These double as Gemini structured-
output schemas (passed directly as response_schema) and as the on-disk JSON
shape for output/prep/*.json.

Only question_plan.json's shape is fixed by the PRD (section 4) -- jd.json,
resume.json, and github.json are designed here to carry what the rest of
the pipeline (gap analysis, question planning, MCP get_candidate) needs.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class JobDescription(BaseModel):
    title: str
    company: str
    location: str
    seniority: str
    responsibilities: list[str]
    required_qualifications: list[str]
    nice_to_have: list[str] = Field(default_factory=list)


class ExperienceEntry(BaseModel):
    title: str
    organization: str
    dates: str
    highlights: list[str]


class ProjectEntry(BaseModel):
    name: str
    description: str
    tech: list[str]
    highlights: list[str]


class EducationEntry(BaseModel):
    degree: str
    institution: str
    dates: str


class Resume(BaseModel):
    name: str
    email: str
    location: str
    github_handle: str
    summary: str
    skills: list[str]
    experience: list[ExperienceEntry]
    projects: list[ProjectEntry]
    education: list[EducationEntry]


class GitHubFile(BaseModel):
    path: str
    excerpt: str


class GitHubCommit(BaseModel):
    sha: str
    message: str
    date: str


class GitHubRepo(BaseModel):
    name: str
    full_name: str
    description: str
    language: str
    url: str
    readme_excerpt: str
    top_files: list[GitHubFile]
    recent_commits: list[GitHubCommit]


class GitHubData(BaseModel):
    username: str
    name: str
    bio: str
    public_repos: int
    repos: list[GitHubRepo]


class Question(BaseModel):
    id: str
    text: str
    competency: str
    source: str  # "github" | "resume" | "jd"
    source_reference: str  # repo/file/commit or resume line -- must be concrete, not generic
    difficulty: str  # "easy" | "medium" | "hard"
    follow_up_triggers: list[str] = Field(default_factory=list)


class QuestionPlan(BaseModel):
    questions: list[Question]
    approved_by_human: bool = False
    edits_made: list[str] = Field(default_factory=list)
