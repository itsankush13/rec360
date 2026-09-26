from pydantic import BaseModel
from typing import Optional, List

class CandidateProfile(BaseModel):
    name: str = "Unknown"
    email: str = ""
    skills: List[str] = []
    experience_years: float = 0.0
    education: str = ""
    projects: List[str] = []
    certifications: List[str] = []
    raw_text: str = ""
    segmented_sections: dict = {}

class ScoringDimension(BaseModel):
    name: str
    score: float  # 0-10
    weight: float
    justification: str

class CandidateScore(BaseModel):
    candidate_name: str
    file_name: str
    dimensions: List[ScoringDimension]
    weighted_total: float
    confidence: float
    hire_recommendation: str  # "STRONG HIRE" / "HIRE" / "MAYBE" / "NO HIRE"
    matched_skills: List[str] = []
    missing_skills: List[str] = []
    semantic_similarity: float = 0.0
    bm25_score: float = 0.0
    bias_masked: bool = True
    hiring_match_pct: float = 0.0   # add this line after bias_masked
    shortlist_reasoning: str = ""
