import fitz  # PyMuPDF
import docx
import re
import spacy
from pathlib import Path

_nlp = None


def _get_nlp():
    """Load spaCy's model on first use, not at import, so importing this
    module doesn't pay the load cost for callers that never extract skills."""
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("en_core_web_sm")
    return _nlp

SECTION_HEADERS = {
    "education": ["education", "academic", "qualification", "degree"],
    "experience": ["experience", "work history", "employment", "career"],
    "skills": ["skills", "technical skills", "competencies", "technologies"],
    "projects": ["projects", "portfolio", "personal projects"],
    "certifications": ["certifications", "certificates", "courses", "licenses"],
    "summary": ["summary", "objective", "profile", "about"],
}

def extract_text_from_pdf(file_path: str) -> str:
    doc = fitz.open(file_path)
    text = ""
    for page in doc:
        text += page.get_text()
    return text.strip()

def extract_text_from_docx(file_path: str) -> str:
    doc = docx.Document(file_path)
    return "\n".join([para.text for para in doc.paragraphs]).strip()

def extract_text(file_path: str) -> str:
    path = Path(file_path)
    if path.suffix.lower() == ".pdf":
        return extract_text_from_pdf(file_path)
    elif path.suffix.lower() in [".docx", ".doc"]:
        return extract_text_from_docx(file_path)
    else:
        raise ValueError(f"Unsupported file type: {path.suffix}")

def segment_resume(text: str) -> dict:
    """Split resume text into labeled sections."""
    lines = text.split("\n")
    sections = {k: [] for k in SECTION_HEADERS}
    sections["other"] = []
    current_section = "other"

    for line in lines:
        line_lower = line.lower().strip()
        matched = False
        for section, keywords in SECTION_HEADERS.items():
            if any(kw in line_lower for kw in keywords) and len(line_lower) < 40:
                current_section = section
                matched = True
                break
        if not matched:
            sections[current_section].append(line)

    return {k: "\n".join(v).strip() for k, v in sections.items()}

def extract_skills_with_spacy(text: str) -> list[str]:
    """Use spaCy NER + pattern matching to extract skills."""
    doc = _get_nlp()(text)
    tech_pattern = re.compile(
        r"\b(python|java|sql|react|node|docker|kubernetes|tensorflow|pytorch|"
        r"langchain|fastapi|aws|azure|gcp|mongodb|postgresql|redis|git|"
        r"machine learning|deep learning|nlp|computer vision|rag|llm|"
        r"scikit-learn|pandas|numpy|transformers|huggingface|mlops|"
        r"langraph|langgraph|crewai|llamaindex|openai|anthropic)\b",
        re.IGNORECASE
    )
    skills = list(set(tech_pattern.findall(text.lower())))
    return [s.title() for s in skills]