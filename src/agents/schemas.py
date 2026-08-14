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


class CompetencyScore(BaseModel):
    name: str
    score: int  # 1-5
    confidence: float  # 0.0-1.0
    evidence_quote: str
    reasoning: str


class Scorecard(BaseModel):
    candidate_name: str
    role: str
    interview_date: str
    duration_seconds: int
    competencies: list[CompetencyScore]
    overall_score: float
    recommendation: str  # "strong_hire" | "hire" | "borderline" | "no_hire"
    recommendation_reasoning: str
    strengths: list[str]
    concerns: list[str]
    guardrail_flags: list[str] = Field(default_factory=list)
    github_grounded_questions_asked: int = 0
