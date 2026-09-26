import re
from typing import Optional

# Prompt injection patterns to block
INJECTION_PATTERNS = [
    r"ignore previous instructions",
    r"system prompt",
    r"act as",
    r"jailbreak",
    r"ignore all",
    r"forget instructions",
    r"new instructions",
    r"override",
]

PII_PATTERNS = {
    "phone": r"\b(\+?\d[\d\s\-().]{7,}\d)\b",
    "email": r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    "aadhaar": r"\b\d{4}\s?\d{4}\s?\d{4}\b",
}

def sanitize_input(text: str) -> tuple[str, list[str]]:
    """Remove prompt injections. Returns (clean_text, list_of_warnings)."""
    warnings = []
    text_lower = text.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text_lower):
            warnings.append(f"Injection pattern detected: '{pattern}'")
            text = re.sub(pattern, "[REDACTED]", text, flags=re.IGNORECASE)
    return text, warnings

def mask_pii(text: str) -> str:
    """Mask PII before sending to LLM."""
    for pii_type, pattern in PII_PATTERNS.items():
        text = re.sub(pattern, f"[{pii_type.upper()}_MASKED]", text, flags=re.IGNORECASE)
    return text

def mask_demographic_info(text: str) -> str:
    """Remove bias-inducing demographic info for fair ranking."""
    patterns = [
        (r"\b(Mr\.|Mrs\.|Ms\.|Dr\.)\s+\w+", "[CANDIDATE]"),
        (r"\b(male|female|he|she|his|her)\b", "[PERSON]"),
        (r"\b(19|20)\d{2}\b(?=.*birth)", "[BIRTH_YEAR]"),
    ]
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text