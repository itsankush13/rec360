from app.core.embeddings import EmbeddingEngine
from app.agents.jd_agent import parse_jd
from typing import List
import numpy as np

engine = EmbeddingEngine()

def match_candidate_to_jds(candidate_text: str, jd_list: List[dict]) -> List[dict]:
    """
    Given a candidate's resume text and a list of parsed JDs,
    return similarity scores for each JD — sorted best first.
    """
    jd_texts = []
    for jd in jd_list:
        # Build a rich JD query string from structured fields
        skills = " ".join(jd["parsed"].get("required_skills", []))
        role = jd["parsed"].get("role_title", "")
        exp = str(jd["parsed"].get("min_experience_years", ""))
        jd_texts.append(f"{role} {skills} {exp} years experience")

    # Embed all JDs + candidate together
    all_texts = jd_texts + [candidate_text]
    embeddings = engine.embed(all_texts)

    cand_emb = embeddings[-1]
    jd_embs = embeddings[:-1]

    results = []
    for i, jd in enumerate(jd_list):
        sim = float(np.dot(cand_emb, jd_embs[i]))
        results.append({
            "jd_id": i,
            "role_name": jd["role_name"],
            "similarity": round(sim, 4),
            "parsed": jd["parsed"],
        })

    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results


def parse_all_jds(jd_inputs: List[dict]) -> List[dict]:
    """
    jd_inputs: [{"role_name": "ML Engineer", "text": "JD text..."}]
    Returns structured parsed JDs.
    """
    parsed_jds = []
    for jd in jd_inputs:
        try:
            parsed = parse_jd(jd["text"])
            parsed_jds.append({
                "role_name": jd["role_name"],
                "text": jd["text"],
                "parsed": parsed,
            })
        except Exception as e:
            print(f"Failed to parse JD '{jd['role_name']}': {e}")
    return parsed_jds