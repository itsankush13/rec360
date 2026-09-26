from rank_bm25 import BM25Okapi
import re
from typing import List

def tokenize(text: str) -> List[str]:
    return re.findall(r'\b\w+\b', text.lower())

class BM25Retriever:
    def __init__(self, documents: List[str]):
        self.documents = documents
        tokenized = [tokenize(doc) for doc in documents]
        self.bm25 = BM25Okapi(tokenized)

    def search(self, query: str, top_k: int = 10) -> List[dict]:
        tokens = tokenize(query)
        scores = self.bm25.get_scores(tokens)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [{"index": i, "bm25_score": float(scores[i])} for i in top_indices]