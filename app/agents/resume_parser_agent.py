from app.core.llm_provider import get_cached_chat_model
from langchain_core.messages import SystemMessage, HumanMessage
from app.core.config import settings
from app.core.security import sanitize_input, mask_pii, mask_demographic_info
from app.utils.document_parser import extract_text, segment_resume, extract_skills_with_spacy
from app.models.candidate import CandidateProfile
import json, re

def _llm():
    # Built on first use, not at import. Importing this module must
    # not require provider credentials.
    return get_cached_chat_model(temperature=0)

PARSE_SYSTEM_PROMPT = """You are a resume parsing expert. Extract structured info from a resume.
Return ONLY valid JSON. No markdown.

JSON structure:
{
  "name": "string or Unknown",
  "email": "string or empty",
  "experience_years": number,
  "education": "highest degree + institution",
  "skills": ["list"],
  "projects": ["brief project descriptions"],
  "certifications": ["list"]
}"""

def parse_resume(file_path: str) -> CandidateProfile:
    raw_text = extract_text(file_path)
    segmented = segment_resume(raw_text)
    
    # Security: mask PII before sending to LLM
    masked_text = mask_pii(raw_text)
    masked_text = mask_demographic_info(masked_text)
    
    clean_text, _ = sanitize_input(masked_text)
    
    # Also extract skills locally with spaCy (faster + offline)
    local_skills = extract_skills_with_spacy(raw_text)
    
    response = _llm().invoke([
        SystemMessage(content=PARSE_SYSTEM_PROMPT),
        HumanMessage(content=f"Resume:\n{clean_text[:6000]}")  # Token limit guard
    ])
    
    text = response.content.strip()
    text = re.sub(r"```json|```", "", text).strip()
    parsed = json.loads(text)
    
    # Merge LLM skills + spaCy skills
    all_skills = list(set(parsed.get("skills", []) + local_skills))
    
    return CandidateProfile(
        name=parsed.get("name", "Unknown"),
        email=parsed.get("email", ""),
        skills=all_skills,
        experience_years=float(parsed.get("experience_years", 0)),
        education=parsed.get("education", ""),
        projects=parsed.get("projects", []),
        certifications=parsed.get("certifications", []),
        raw_text=raw_text,
        segmented_sections=segmented
    )

    from app.utils.linkedin_parser import (
    parse_linkedin_json_export,
    parse_linkedin_text_paste,
    parse_linkedin_rapidapi,
)

def parse_linkedin_to_profile(linkedin_data: dict) -> CandidateProfile:
    """
    Convert parsed LinkedIn dict → CandidateProfile
    (same model used for resumes, so pipeline treats them identically)
    """
    local_skills = extract_skills_with_spacy(linkedin_data.get("raw_text",""))
    all_skills = list(set(linkedin_data.get("skills",[]) + local_skills))

    return CandidateProfile(
        name=linkedin_data.get("name","Unknown"),
        email="",
        skills=all_skills,
        experience_years=float(linkedin_data.get("experience_years", 0)),
        education=linkedin_data.get("education",""),
        projects=linkedin_data.get("projects",[]),
        certifications=linkedin_data.get("certifications",[]),
        raw_text=linkedin_data.get("raw_text",""),
        segmented_sections={
            "experience": linkedin_data.get("experience_text",""),
            "education":  linkedin_data.get("education",""),
            "skills":     ", ".join(linkedin_data.get("skills",[])),
        }
    )