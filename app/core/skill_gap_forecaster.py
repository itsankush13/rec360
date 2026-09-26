from sentence_transformers import SentenceTransformer
import numpy as np
from typing import List

model = SentenceTransformer("all-MiniLM-L6-v2")

# Skills grouped by learning adjacency
SKILL_CLUSTERS = {
    "ml_core": ["python", "numpy", "pandas", "scikit-learn", "statistics"],
    "deep_learning": ["tensorflow", "pytorch", "keras", "transformers", "cuda"],
    "mlops": ["docker", "kubernetes", "mlflow", "airflow", "ci/cd", "github actions"],
    "llm_ai": ["langchain", "langgraph", "openai", "huggingface", "rag", "vector db", "faiss"],
    "data_eng": ["sql", "spark", "kafka", "airflow", "dbt", "postgresql"],
    "cloud": ["aws", "gcp", "azure", "s3", "ec2", "lambda"],
    "backend": ["fastapi", "flask", "django", "rest api", "graphql"],
}

def get_skill_cluster(skill: str) -> str:
    skill_lower = skill.lower()
    for cluster, skills in SKILL_CLUSTERS.items():
        if any(s in skill_lower or skill_lower in s for s in skills):
            return cluster
    return "general"

def compute_transferability(candidate_skills: List[str], missing_skills: List[str]) -> dict:
    """
    Estimate how quickly a candidate can learn missing skills
    based on semantic proximity to their existing skills.
    """
    if not candidate_skills or not missing_skills:
        return {"adaptability": "UNKNOWN", "months_estimate": "N/A", "readiness_score": 0}
    
    cand_embeddings = model.encode(candidate_skills, normalize_embeddings=True)
    miss_embeddings = model.encode(missing_skills, normalize_embeddings=True)
    
    # For each missing skill, find max similarity to any known skill
    transferability_scores = []
    skill_details = []
    
    for i, miss_skill in enumerate(missing_skills):
        sims = np.dot(cand_embeddings, miss_embeddings[i])
        max_sim = float(np.max(sims))
        closest = candidate_skills[int(np.argmax(sims))]
        transferability_scores.append(max_sim)
        skill_details.append({
            "missing": miss_skill,
            "closest_known": closest,
            "transferability": round(max_sim, 3),
            "cluster": get_skill_cluster(miss_skill)
        })
    
    avg_transfer = float(np.mean(transferability_scores))
    
    # Check cluster overlap (same cluster = faster learning)
    cand_clusters = set(get_skill_cluster(s) for s in candidate_skills)
    miss_clusters = set(get_skill_cluster(s) for s in missing_skills)
    cluster_overlap = len(cand_clusters & miss_clusters) / max(len(miss_clusters), 1)
    
    # Composite adaptability score
    adapt_score = (avg_transfer * 0.6 + cluster_overlap * 0.4)
    
    if adapt_score > 0.7:
        adaptability = "HIGH"
        months = "1–2 months"
        readiness = min(95, int(60 + adapt_score * 40))
    elif adapt_score > 0.45:
        adaptability = "MEDIUM"
        months = "2–4 months"
        readiness = min(80, int(40 + adapt_score * 40))
    else:
        adaptability = "LOW"
        months = "4–6+ months"
        readiness = int(adapt_score * 50)
    
    return {
        "adaptability": adaptability,
        "months_estimate": months,
        "readiness_score": readiness,
        "avg_transferability": round(avg_transfer, 3),
        "cluster_overlap": round(cluster_overlap, 3),
        "skill_details": skill_details
    }