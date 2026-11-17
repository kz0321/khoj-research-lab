from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator

Mode = Literal["no_tools", "single_rag", "multi_step", "verified", "verified_no_repair"]

class ResearchRequest(BaseModel):
    question: str = Field(min_length=3, max_length=3000)
    collection_id: str = Field(default="demo", max_length=100)
    mode: Mode = "verified"
    allow_web: bool = False
    perturbation: dict[str, Any] | None = None

class ToolAction(BaseModel):
    name: Literal["semantic_search_files", "view_file", "search_web", "read_webpage"]
    args: dict[str, Any] = Field(default_factory=dict)

class Decision(BaseModel):
    subquestions: list[str] = Field(default_factory=list, max_length=6)
    evidence_needed: list[str] = Field(default_factory=list, max_length=8)
    actions: list[ToolAction] = Field(default_factory=list, max_length=2)
    done: bool = False
    summary: str = ""

class Claim(BaseModel):
    id: str
    text: str = Field(max_length=1600)
    evidence_ids: list[str] = Field(default_factory=list, max_length=8)

class AnswerClaim(Claim):
    """The summary may combine references from several individual claims."""
    evidence_ids: list[str] = Field(default_factory=list, max_length=30)

class Draft(BaseModel):
    answer: str = Field(default="", max_length=1400)
    answer_statement: str = Field(default="", max_length=1600)
    # A research summary can cite the union of several separately bounded
    # claims. Match the run's evidence cap instead of rejecting valid reviews.
    answer_evidence_ids: list[str] = Field(default_factory=list, max_length=30)
    claims: list[Claim] = Field(default_factory=list, max_length=8)
    unresolved: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("claims")
    @classmethod
    def unique_ids(cls, claims):
        ids = [c.id for c in claims]
        if len(ids) != len(set(ids)) or "A0" in ids:
            raise ValueError("Claim IDs must be unique and A0 is reserved")
        return claims

class Verdict(BaseModel):
    claim_id: str
    status: Literal["supported", "contradicted", "insufficient"]
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)
    quotes: list[str] = Field(default_factory=list)

class Verification(BaseModel):
    verdicts: list[Verdict] = Field(default_factory=list)
    followup_queries: list[str] = Field(default_factory=list, max_length=2)

class DocumentInput(BaseModel):
    id: str | None = Field(default=None, max_length=200)
    title: str = Field(min_length=1, max_length=500)
    text: str = Field(max_length=2_000_000)
    sentences: list[Any] | None = None
    url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class ImportRequest(BaseModel):
    documents: list[DocumentInput] = Field(min_length=1, max_length=100)

class CollectionInput(BaseModel):
    id: str | None = Field(default=None, max_length=100, pattern=r"^[\w.-]+$")
    name: str = Field(min_length=1, max_length=200)
