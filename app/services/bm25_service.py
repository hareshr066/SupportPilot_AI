import re
import math
import json
import logging
from pathlib import Path
from collections import Counter, defaultdict
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

ENGLISH_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "because", "as", "what",
    "which", "this", "that", "these", "those", "then", "just", "so", "than",
    "such", "both", "through", "about", "against", "between", "into", "throughout",
    "during", "before", "after", "above", "below", "to", "from", "up", "upon",
    "down", "in", "out", "on", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "any", "both",
    "each", "few", "more", "most", "other", "some", "such", "no", "nor", "not",
    "only", "own", "same", "so", "than", "too", "very", "can", "will", "don",
    "should", "now"
}

TECHNICAL_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_\-\.\:\/]+")


def tokenize_technical_text(text: str) -> List[str]:
    """
    Tokenizes technical text preserving error codes, version strings, package names,
    class names, API endpoints, and configuration identifiers.
    
    Examples preserved:
    - ERR_CONNECTION_RESET
    - NullPointerException
    - OAuth2
    - v2.4.1
    - postgresql
    - WebSocket
    """
    if not text:
        return []
    
    raw_tokens = TECHNICAL_TOKEN_PATTERN.findall(text)
    tokens = []
    for token in raw_tokens:
        token_lower = token.lower().strip(".-:")
        if not token_lower or len(token_lower) < 2:
            continue
        # Only remove if strictly in generic non-technical English stopwords
        if token_lower in ENGLISH_STOPWORDS and not any(c.isdigit() for c in token_lower):
            continue
        tokens.append(token_lower)
    return tokens


class BM25Index:
    """
    Pure-Python Okapi BM25 implementation for lexical retrieval over technical support documents.
    Supports index persistence to disk, fast term matching, and score retrieval.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_ids: List[int] = []  # Internal doc_id -> issue_id
        self.doc_lengths: List[int] = []
        self.avgdl: float = 0.0
        self.corpus_size: int = 0
        self.doc_term_freqs: List[Dict[str, int]] = []
        self.inverted_index: Dict[str, List[Tuple[int, int]]] = defaultdict(list)
        self.idf: Dict[str, float] = {}

    def fit(self, documents: List[Dict[str, Any]]) -> None:
        """
        Builds the BM25 index from structured canonical documents.
        Each document dict must have 'issue_id' and 'canonical_text'.
        """
        self.corpus_size = len(documents)
        if self.corpus_size == 0:
            self.avgdl = 0.0
            return

        self.doc_ids = []
        self.doc_lengths = []
        self.doc_term_freqs = []
        self.inverted_index.clear()
        self.idf.clear()

        total_length = 0
        df = Counter()

        for idx, doc in enumerate(documents):
            issue_id = doc["issue_id"]
            text = doc.get("canonical_text", "")
            tokens = tokenize_technical_text(text)
            doc_len = len(tokens)

            self.doc_ids.append(issue_id)
            self.doc_lengths.append(doc_len)
            total_length += doc_len

            term_counts = Counter(tokens)
            self.doc_term_freqs.append(dict(term_counts))

            for term, count in term_counts.items():
                self.inverted_index[term].append((idx, count))
                df[term] += 1

        self.avgdl = total_length / self.corpus_size if self.corpus_size > 0 else 0.0

        # Calculate IDF for all vocabulary terms
        for term, freq in df.items():
            # BM25 IDF formula with smoothing
            idf_val = math.log((self.corpus_size - freq + 0.5) / (freq + 0.5) + 1.0)
            self.idf[term] = max(0.0, idf_val)

        logger.info(
            f"BM25 Index Built: {self.corpus_size} docs, "
            f"vocab_size={len(self.idf)}, avgdl={self.avgdl:.2f}"
        )

    def search(
        self,
        query_text: str,
        top_k: int = 50,
        eligible_doc_ids: Optional[set] = None
    ) -> List[Tuple[int, float]]:
        """
        Searches the BM25 index for query_text.
        Returns a list of tuples: (issue_id, bm25_score) sorted by score descending.
        """
        if not query_text or self.corpus_size == 0:
            return []

        query_tokens = tokenize_technical_text(query_text)
        if not query_tokens:
            return []

        scores = defaultdict(float)

        for term in query_tokens:
            if term not in self.idf:
                continue
            idf_val = self.idf[term]
            postings = self.inverted_index[term]

            for doc_idx, tf in postings:
                issue_id = self.doc_ids[doc_idx]
                if eligible_doc_ids is not None and issue_id not in eligible_doc_ids:
                    continue

                doc_len = self.doc_lengths[doc_idx]
                denom = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / self.avgdl))
                score_contrib = idf_val * ((tf * (self.k1 + 1.0)) / denom)
                scores[issue_id] += score_contrib

        sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_results[:top_k]

    def save(self, filepath: Path) -> None:
        """Saves the index to disk as a JSON artifact."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "k1": self.k1,
            "b": self.b,
            "corpus_size": self.corpus_size,
            "avgdl": self.avgdl,
            "doc_ids": self.doc_ids,
            "doc_lengths": self.doc_lengths,
            "idf": self.idf,
            "inverted_index": {
                term: postings for term, postings in self.inverted_index.items()
            }
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f)
        logger.info(f"BM25 Index saved to {filepath}")

    @classmethod
    def load(cls, filepath: Path) -> "BM25Index":
        """Loads a BM25 index from a saved JSON artifact."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        idx_obj = cls(k1=data["k1"], b=data["b"])
        idx_obj.corpus_size = data["corpus_size"]
        idx_obj.avgdl = data["avgdl"]
        idx_obj.doc_ids = data["doc_ids"]
        idx_obj.doc_lengths = data["doc_lengths"]
        idx_obj.idf = data["idf"]
        idx_obj.inverted_index = defaultdict(
            list,
            {k: [tuple(p) for p in v] for k, v in data["inverted_index"].items()}
        )
        logger.info(f"BM25 Index loaded from {filepath} ({idx_obj.corpus_size} docs)")
        return idx_obj
