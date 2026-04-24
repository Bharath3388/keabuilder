"""Minimal similarity matcher for KeaBuilder.

Matches a query against a small set of sample inputs using cosine similarity.
Works with raw text (TF-IDF vectorisation) — no external model needed.

Usage:
    python -m utils.similarity_matcher "build me a landing page"
"""

from __future__ import annotations

import math
import re
import sys
from collections import Counter
from typing import Sequence

# ---------------------------------------------------------------------------
# Sample inputs (leads / prompts that might appear in KeaBuilder)
# ---------------------------------------------------------------------------
SAMPLES: list[str] = [
    "I need a high-converting landing page for my SaaS product launch",
    "Generate a short promotional video for our new sneaker line",
    "Create a professional voice-over for a product walkthrough",
    "Design an email funnel to nurture trial users into paid customers",
    "Build a lead capture form with smart follow-up automation",
]


# ---------------------------------------------------------------------------
# Vectorisation helpers (simple term-frequency, no dependencies)
# ---------------------------------------------------------------------------
_SPLIT = re.compile(r"\W+")


def _tokenize(text: str) -> list[str]:
    return [w.lower() for w in _SPLIT.split(text) if w]


def _term_freq(tokens: list[str]) -> Counter:
    return Counter(tokens)


def _build_vocab(docs: Sequence[str]) -> list[str]:
    vocab: set[str] = set()
    for doc in docs:
        vocab.update(_tokenize(doc))
    return sorted(vocab)


def _vectorize(text: str, vocab: list[str]) -> list[float]:
    tf = _term_freq(_tokenize(text))
    return [float(tf.get(w, 0)) for w in vocab]


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------
def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def find_best_match(
    query: str,
    samples: Sequence[str] | None = None,
) -> dict:
    """Return the most similar sample to *query*.

    Returns dict with keys: query, best_match, similarity, rank (all results).
    """
    samples = list(samples or SAMPLES)
    vocab = _build_vocab([query, *samples])
    q_vec = _vectorize(query, vocab)

    scored = []
    for text in samples:
        s_vec = _vectorize(text, vocab)
        scored.append((cosine_similarity(q_vec, s_vec), text))

    scored.sort(key=lambda t: t[0], reverse=True)

    return {
        "query": query,
        "best_match": scored[0][1],
        "similarity": round(scored[0][0], 4),
        "rankings": [
            {"text": text, "similarity": round(sim, 4)}
            for sim, text in scored
        ],
    }


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "landing page for my startup"
    result = find_best_match(query)

    print(f"\nQuery : {result['query']}")
    print(f"Match : {result['best_match']}")
    print(f"Score : {result['similarity']}\n")
    print("All rankings:")
    for i, r in enumerate(result["rankings"], 1):
        print(f"  {i}. [{r['similarity']:.4f}] {r['text']}")
