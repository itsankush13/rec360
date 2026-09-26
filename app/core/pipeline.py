import os
from app.agents.jd_agent import parse_jd
from app.agents.resume_parser_agent import parse_resume
from app.agents.scoring_agent import score_candidate
from app.agents.bias_audit_agent import audit_for_bias
from app.agents.challenge_agent import challenge_score
from app.core.embeddings import EmbeddingEngine
from app.core.bm25_retriever import BM25Retriever
from app.core.multi_jd_matcher import match_candidate_to_jds, parse_all_jds
from app.models.candidate import CandidateScore
from typing import List


def run_pipeline(jd_text: str, resume_files: List[str],
                 extra_jds: List[dict] = None,
                 linkedin_profiles: List = None) -> List[dict]:
    """
    extra_jds: [{"role_name": "Data Engineer", "text": "..."}]
    """
    print("[1/6] Parsing Primary Job Description...")
    primary_jd = parse_jd(jd_text)
    primary_role = primary_jd.get("role_title", "Primary Role")
    jd_query = " ".join(primary_jd.get("required_skills", []) +
                        [primary_role])

    # Build full JD list including primary
    all_jd_inputs = [{"role_name": primary_role, "text": jd_text}]
    if extra_jds:
        all_jd_inputs += extra_jds

    print(f"[1b/6] Parsing {len(all_jd_inputs)} JDs total...")
    all_jds_parsed = parse_all_jds(all_jd_inputs)

    print("[2/6] Parsing Resumes...")
    candidates = []
    for f in resume_files:
        try:
            profile = parse_resume(f)
            candidates.append({"profile": profile, "file": os.path.basename(f)})
            print(f"  [ok] Parsed: {profile.name}")
        except Exception as e:
            print(f"  [fail] {f}: {e}")

    if not candidates:
        return []

    print("[3/6] Building Embedding Index...")
    resume_texts = [c["profile"].raw_text for c in candidates]
    engine = EmbeddingEngine()
    engine.add_candidates(resume_texts)
    bm25 = BM25Retriever(resume_texts)

    print("[4/6] Hybrid Retrieval (FAISS + BM25)...")
    sem_results = engine.search(jd_query, top_k=len(candidates))
    bm25_results = bm25.search(jd_query, top_k=len(candidates))
    sem_scores = {r["index"]: r["similarity_score"] for r in sem_results}
    bm25_map = {r["index"]: r["bm25_score"] for r in bm25_results}

    print("[5/6] Scoring + Multi-JD Matching...")
    results = []
    for i, cand in enumerate(candidates):
        profile = cand["profile"]
        score: CandidateScore = score_candidate(
            profile, primary_jd,
            sem_scores.get(i, 0.0), bm25_map.get(i, 0.0)
        )
        score.file_name = cand["file"]
        audit = audit_for_bias(
            score.shortlist_reasoning,
            profile.name,
            profile.raw_text        # ← pass raw text so bias agent can scan it
        )
        challenge_audit = challenge_score(score, profile)

        # Multi-JD matching
        jd_matches = match_candidate_to_jds(profile.raw_text, all_jds_parsed)

        results.append({
            "score": score,
            "profile": profile,
            "jd": primary_jd,
            "bias_audit": audit,
            "challenge_audit": challenge_audit,
            "jd_matches": jd_matches,          # ← NEW
            "all_jds": all_jds_parsed,          # ← NEW
        })
        best = jd_matches[0]["role_name"] if jd_matches else "N/A"
        print(f"  [ok] {profile.name} -> {score.weighted_total}/10 | Best fit: {best}")

    print("[6/6] Ranking...")
    results.sort(key=lambda x: x["score"].weighted_total, reverse=True)
    return results
    # Add LinkedIn profiles into the same candidate list
    for profile in (linkedin_profiles or []):
        candidates.append({"profile": profile, "file": f"LinkedIn: {profile.name}"})
        print(f"  [ok] LinkedIn profile added: {profile.name}")