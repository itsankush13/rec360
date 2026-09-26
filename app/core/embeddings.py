import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from typing import List

# Using a strong open-source embedding model
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

class EmbeddingEngine:
    def __init__(self):
        self.model = SentenceTransformer(EMBEDDING_MODEL)
        self.dimension = 384  # for MiniLM
        self.index = faiss.IndexFlatIP(self.dimension)  # Inner product = cosine after norm
        self.stored_texts = []

    def embed(self, texts: List[str]) -> np.ndarray:
        embeddings = self.model.encode(texts, normalize_embeddings=True)
        return embeddings.astype(np.float32)

    def add_candidates(self, texts: List[str]):
        self.stored_texts = texts
        embeddings = self.embed(texts)
        self.index.add(embeddings)

    def search(self, query: str, top_k: int = 10) -> List[dict]:
        query_emb = self.embed([query])
        scores, indices = self.index.search(query_emb, top_k)
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx != -1:
                results.append({
                    "index": int(idx),
                    "text": self.stored_texts[idx],
                    "similarity_score": float(score)
                })
        return results

    def cosine_similarity(self, text1: str, text2: str) -> float:
        embs = self.embed([text1, text2])
        return float(np.dot(embs[0], embs[1]))