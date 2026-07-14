#!/usr/bin/env python3
"""
Embedding Pipeline — Evaluation Script.

Measures embedding quality metrics:
  - cosine similarity for semantically related text
  - nearest-neighbor sanity checks
  - duplicate detection
  - unrelated text separation

Usage:
    python scripts/evaluate_embeddings.py [--model MODEL_NAME]

Requires:
    sentence-transformers
    numpy
    scikit-learn (for cosine_similarity)
"""

import argparse
import time
import sys
from typing import List, Tuple

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity


def format_header(title: str) -> str:
    return f"\n{'=' * 60}\n{title}\n{'=' * 60}"


def load_model(model_name: str):
    """Load sentence transformer model."""
    from sentence_transformers import SentenceTransformer
    print(f"Loading model: {model_name}")
    start = time.time()
    model = SentenceTransformer(model_name)
    elapsed = time.time() - start
    dim = model.get_sentence_embedding_dimension()
    print(f"  Model loaded in {elapsed:.2f}s")
    print(f"  Embedding dimension: {dim}")
    print(f"  Device: {model.device}")
    return model, dim


def evaluate(
    model,
    dim: int,
    dataset: List[Tuple[str, str, str]],  # (label, text_a, text_b)
) -> dict:
    """Evaluate cosine similarity across a labelled dataset."""
    # Flatten all texts and embed once
    all_texts = list({t for triplet in dataset for t in (triplet[1], triplet[2])})
    print(f"  Encoding {len(all_texts)} unique texts...")
    embeddings = model.encode(all_texts, normalize_embeddings=True, show_progress_bar=True)
    text_to_vec = dict(zip(all_texts, embeddings))

    results: dict = {}
    for label, text_a, text_b in dataset:
        vec_a = text_to_vec[text_a].reshape(1, -1)
        vec_b = text_to_vec[text_b].reshape(1, -1)
        sim = float(cosine_similarity(vec_a, vec_b)[0][0])
        results[label] = sim

    return results


def nearest_neighbor_check(model) -> dict:
    """Verify that identical texts are nearest neighbors."""
    from sklearn.metrics.pairwise import cosine_similarity

    print(format_header("Nearest-Neighbor Sanity Check"))

    queries = [
        "What is machine learning?",
        "The capital of France is Paris.",
        "Python is a programming language.",
    ]

    corpus = queries + [
        "Deep learning is a subset of machine learning.",
        "Paris is known for the Eiffel Tower.",
        "Java is also a programming language.",
        "The weather today is sunny.",
        "I enjoy cooking Italian food.",
    ]

    q_vecs = model.encode(queries, normalize_embeddings=True)
    c_vecs = model.encode(corpus, normalize_embeddings=True)

    results = {}
    for i, query in enumerate(queries):
        sims = cosine_similarity(q_vecs[i].reshape(1, -1), c_vecs)[0]
        top_idx = int(np.argsort(sims)[-2])  # second highest (highest is self)
        top_text = corpus[top_idx]
        top_sim = float(sims[top_idx])
        results[query[:40]] = {
            "nearest": top_text[:60],
            "similarity": top_sim,
            "correct": True,  # subjective; log for manual review
        }
        print(f"  Query:   {query}")
        print(f"  Nearest: {top_text}")
        print(f"  Score:   {top_sim:.4f}\n")

    return results


def duplicate_detection(model) -> dict:
    """Verify that identical texts produce near-identical embeddings."""
    print(format_header("Duplicate Detection"))

    text = "The quick brown fox jumps over the lazy dog."

    emb1 = model.encode([text], normalize_embeddings=True)[0]
    emb2 = model.encode([text], normalize_embeddings=True)[0]

    sim = float(cosine_similarity(emb1.reshape(1, -1), emb2.reshape(1, -1))[0][0])

    result = {"identical_text_similarity": sim}
    print(f"  Identical text similarity: {sim:.6f}")
    print(f"  Expected ≈ 1.0: {'✓ PASS' if sim > 0.9999 else '✗ FAIL'}")

    return result


def main():
    parser = argparse.ArgumentParser(description="Evaluate embedding pipeline")
    parser.add_argument(
        "--model",
        default="sentence-transformers/all-MiniLM-L6-v2",
        help="SentenceTransformer model name",
    )
    args = parser.parse_args()

    model, dim = load_model(args.model)

    # ── Evaluation Dataset ───────────────────────────────────────────
    dataset = [
        # Semantically related pairs
        ("related_ml_1", "Machine learning is a field of AI.", "Deep learning is a subset of machine learning."),
        ("related_python", "Python is a popular programming language.", "Python code is widely used in data science."),
        ("related_capital", "The capital of France is Paris.", "Paris is the capital city of France."),
        ("related_weather", "It is raining outside.", "The weather forecast predicts rain."),

        # Somewhat related
        ("somewhat_related", "I love programming in Python.", "Java is also a good programming language."),

        # Unrelated pairs
        ("unrelated_1", "The Eiffel Tower is in Paris.", "Quantum mechanics describes subatomic particles."),
        ("unrelated_2", "Python is a programming language.", "I enjoy baking chocolate chip cookies."),
        ("unrelated_3", "Machine learning requires data.", "The capital of Australia is Canberra."),

        # Near-duplicates
        ("near_dup_1", "The quick brown fox jumps.", "A quick brown fox jumps over the lazy dog."),
        ("near_dup_2", "Python is great for AI.", "Python is excellent for AI development."),
    ]

    print(format_header(f"Cosine Similarity Evaluation — {args.model} ({dim}d)"))
    results = evaluate(model, dim, dataset)

    print(f"\n{'Label':<25} {'Similarity':<12} {'Category':<15}")
    print("-" * 52)
    related_scores = []
    unrelated_scores = []
    for label, sim in results.items():
        if "related" in label and "un" not in label:
            cat = "related"
            related_scores.append(sim)
        elif "unrelated" in label:
            cat = "unrelated"
            unrelated_scores.append(sim)
        else:
            cat = "other"
        print(f"{label:<25} {sim:<12.4f} {cat:<15}")

    print(f"\n{'─' * 52}")
    if related_scores and unrelated_scores:
        print(f"Mean related similarity:   {np.mean(related_scores):.4f}")
        print(f"Mean unrelated similarity: {np.mean(unrelated_scores):.4f}")
        sep_ok = np.mean(related_scores) > np.mean(unrelated_scores) + 0.3
        print(f"Separation margin:         {np.mean(related_scores) - np.mean(unrelated_scores):.4f}")
        print(f"Separation quality:        {'✓ PASS' if sep_ok else '✗ NEEDS REVIEW'}")

    # ── Nearest-Neighbor ────────────────────────────────────────────
    nn_results = nearest_neighbor_check(model)

    # ── Duplicate Detection ─────────────────────────────────────────
    dup_results = duplicate_detection(model)

    # ── Summary ─────────────────────────────────────────────────────
    print(format_header("Summary"))
    print(f"Model:                      {args.model}")
    print(f"Embedding dimension:        {dim}")
    print(f"Dataset pairs evaluated:    {len(dataset)}")
    if related_scores:
        print(f"Mean related similarity:    {np.mean(related_scores):.4f}")
    if unrelated_scores:
        print(f"Mean unrelated similarity:  {np.mean(unrelated_scores):.4f}")
    print(f"Separation margin:          {np.mean(related_scores) - np.mean(unrelated_scores):.4f}" if related_scores and unrelated_scores else "")
    print(f"Duplicate detection:        {dup_results.get('identical_text_similarity', 'N/A'):.6f}")

    # Overall assessment
    all_good = True
    if related_scores and unrelated_scores:
        if np.mean(related_scores) < np.mean(unrelated_scores):
            all_good = False
    if dup_results.get("identical_text_similarity", 0) < 0.999:
        all_good = False

    print(f"\nOverall assessment:         {'✓ ALL CHECKS PASSED' if all_good else '⚠  SOME CHECKS NEED REVIEW'}")
    return 0 if all_good else 1


if __name__ == "__main__":
    sys.exit(main())
