from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TranslationRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    source_language: str = Field(pattern="^(en|hi|kn|ta|ml|te)$")
    target_language: str = Field(pattern="^(en|hi|kn|ta|ml|te)$")
    max_candidates: int = Field(default=3, ge=1, le=5)


class CandidateScore(BaseModel):
    entities: float
    length: float
    target_script: float
    tonality: float
    semantic: float
    fluency: float
    confidence: float
    total: float


class TranslationCandidate(BaseModel):
    candidate_id: str
    strategy: str
    text: str
    confidence: float
    score: float
    breakdown: CandidateScore
    notes: list[str] = Field(default_factory=list)
    model_config = ConfigDict(arbitrary_types_allowed=True)


class TranslationResponse(BaseModel):
    source_language: str
    target_language: str
    pair_label: str
    input_text: str
    selected_candidate: TranslationCandidate
    candidates: list[TranslationCandidate]
    model_status: str
    retry_used: bool
    diagnostics: dict[str, Any]


class HealthResponse(BaseModel):
    status: str
    model_status: str
    mode: str
    safetensors: bool
    hf_transfer: bool
