"""
precompute_embeddings.py — Offline Embedding Generation
=======================================================
Reads candidates.jsonl (100k records), builds a text blob per candidate,
embeds everything with all-MiniLM-L6-v2 (384-dim, CPU), and writes:

  1. candidate_embeddings.parquet  — candidate_id + embedding[384]
  2. jd_facet_embeddings.npy       — (12, 384) float32
  3. jd_facet_metadata.json        — 12 facet dicts (label/text/polarity/tier)

Usage:
    pip install sentence-transformers pyarrow tqdm numpy
    python precompute_embeddings.py --candidates candidates.jsonl --out-dir .
"""

import argparse
import json
import os
import time

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from tqdm import tqdm


# ──────────────────────────────────────────────────────────────────────
# JD FACET DEFINITIONS (12 total: 4 core + 5 bonus + 3 penalty)
# Row order here is the canonical order for the .npy and .json outputs.
# ──────────────────────────────────────────────────────────────────────

JD_FACETS = [
    # ── CORE (must-haves) ─────────────────────────────────────────────
    {
        "label": "retrieval_systems",
        "text": (
            "Production experience with embeddings-based retrieval systems "
            "deployed to real users, handling embedding drift, index refresh, "
            "and retrieval-quality regression."
        ),
        "polarity": "positive",
        "tier": "core",
    },
    {
        "label": "vector_db_search",
        "text": (
            "Production experience with vector databases or hybrid search "
            "infrastructure such as Pinecone, Weaviate, Qdrant, Milvus, "
            "OpenSearch, Elasticsearch, or FAISS."
        ),
        "polarity": "positive",
        "tier": "core",
    },
    {
        "label": "python_engineering",
        "text": (
            "Strong Python software engineering with high code quality, "
            "used to build production machine learning systems."
        ),
        "polarity": "positive",
        "tier": "core",
    },
    {
        "label": "ranking_evaluation",
        "text": (
            "Designed evaluation frameworks for ranking systems, including "
            "NDCG, MRR, MAP, offline-to-online correlation, and A/B test "
            "interpretation."
        ),
        "polarity": "positive",
        "tier": "core",
    },
    # ── BONUS (good-to-haves) ─────────────────────────────────────────
    {
        "label": "llm_finetuning",
        "text": (
            "LLM fine-tuning experience using LoRA, QLoRA, or PEFT techniques."
        ),
        "polarity": "positive",
        "tier": "bonus",
    },
    {
        "label": "learning_to_rank",
        "text": (
            "Experience building learning-to-rank models, either "
            "XGBoost-based or neural network based."
        ),
        "polarity": "positive",
        "tier": "bonus",
    },
    {
        "label": "hr_recruiting_marketplace",
        "text": (
            "Prior experience working on HR technology, recruiting "
            "technology, or marketplace products."
        ),
        "polarity": "positive",
        "tier": "bonus",
    },
    {
        "label": "distributed_systems",
        "text": (
            "Background in distributed systems or large-scale machine "
            "learning inference optimization."
        ),
        "polarity": "positive",
        "tier": "bonus",
    },
    {
        "label": "open_source",
        "text": (
            "Open-source contributions in the AI or machine learning space."
        ),
        "polarity": "positive",
        "tier": "bonus",
    },
    # ── PENALTY (don't-wants) ─────────────────────────────────────────
    {
        "label": "framework_enthusiast",
        "text": (
            "No production systems built. Experience consists entirely of "
            "following online tutorials, writing blog posts about testing new "
            "APIs like LangChain or OpenAI, and building demo projects with no "
            "real users, no scale, and no engineering depth beyond gluing "
            "together existing libraries."
        ),
        "polarity": "negative",
        "tier": "penalty",
    },
    {
        "label": "cv_speech_robotics",
        "text": (
            "Primary expertise in computer vision, speech recognition, or "
            "robotics, without significant natural language processing or "
            "information retrieval exposure."
        ),
        "polarity": "negative",
        "tier": "penalty",
    },
    {
        "label": "closed_source_only",
        "text": (
            "Career spent entirely on closed-source proprietary internal "
            "systems with no external validation such as publications, "
            "conference talks, or open-source work."
        ),
        "polarity": "negative",
        "tier": "penalty",
    },
]


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def build_candidate_text(record: dict) -> str:
    """
    Combine headline, summary, and career-history descriptions into a
    single text blob for embedding.  Every field is optional — missing
    or malformed values fall back to empty string so we never crash.
    """
    profile = record.get("profile") or {}
    headline = profile.get("headline") or ""
    summary = profile.get("summary") or ""

    career = record.get("career_history") or []
    descriptions = []
    for entry in career:
        if isinstance(entry, dict):
            desc = entry.get("description") or ""
            if desc:
                descriptions.append(desc)

    career_text = " ".join(descriptions)
    return f"{headline}. {summary} {career_text}".strip()


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Precompute candidate + JD-facet embeddings"
    )
    parser.add_argument(
        "--candidates", required=True,
        help="Path to candidates.jsonl (100k records)",
    )
    parser.add_argument(
        "--out-dir", default=".",
        help="Directory for output files (default: cwd)",
    )
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    t_global = time.perf_counter()

    # ── 1. Load the embedding model ──────────────────────────────────
    print("=" * 60)
    print("  Loading sentence-transformers model (all-MiniLM-L6-v2)")
    print("=" * 60)
    t0 = time.perf_counter()

    from sentence_transformers import SentenceTransformer  # noqa: E402
    model = SentenceTransformer("all-MiniLM-L6-v2")

    print(f"  Model loaded in {time.perf_counter() - t0:.1f}s")
    print(f"  Embedding dimension: {model.get_sentence_embedding_dimension()}")

    # ── 2. Read candidates and build text blobs ──────────────────────
    print("\n" + "=" * 60)
    print("  Reading candidates.jsonl")
    print("=" * 60)
    t0 = time.perf_counter()

    candidate_ids: list[str] = []
    candidate_texts: list[str] = []

    with open(args.candidates, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                # Skip malformed lines — log and continue
                print(f"  WARNING: skipping malformed JSON at line {line_no}")
                continue

            cid = record.get("candidate_id", f"UNKNOWN_{line_no}")
            text = build_candidate_text(record)

            candidate_ids.append(cid)
            candidate_texts.append(text)

    n_candidates = len(candidate_ids)
    print(f"  Read {n_candidates:,} candidates in {time.perf_counter() - t0:.1f}s")

    # ── 3. Embed candidate text blobs (batched) ──────────────────────
    print("\n" + "=" * 60)
    print("  Embedding candidates (batch_size=64, CPU)")
    print("=" * 60)
    t0 = time.perf_counter()

    BATCH_SIZE = 64
    all_embeddings: list[np.ndarray] = []

    for i in tqdm(range(0, n_candidates, BATCH_SIZE), desc="Embedding", unit="batch"):
        batch_texts = candidate_texts[i : i + BATCH_SIZE]
        batch_emb = model.encode(
            batch_texts,
            batch_size=BATCH_SIZE,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        all_embeddings.append(batch_emb)

        # Periodic timing log every 500 batches (~32k candidates)
        if (i // BATCH_SIZE) % 500 == 0 and i > 0:
            elapsed = time.perf_counter() - t0
            done = min(i + BATCH_SIZE, n_candidates)
            rate = done / elapsed
            eta = (n_candidates - done) / rate if rate > 0 else 0
            print(f"  ... {done:,}/{n_candidates:,} done — "
                  f"{elapsed:.0f}s elapsed, ETA {eta:.0f}s")

    # Stack into a single (N, 384) matrix
    embedding_matrix = np.vstack(all_embeddings).astype(np.float32)
    embed_time = time.perf_counter() - t0
    print(f"  Embedded {n_candidates:,} candidates in {embed_time:.1f}s "
          f"({n_candidates / embed_time:.0f} candidates/s)")
    print(f"  Matrix shape: {embedding_matrix.shape}")

    # ── 4. Embed JD facet texts ──────────────────────────────────────
    print("\n" + "=" * 60)
    print("  Embedding 12 JD facets")
    print("=" * 60)
    t0 = time.perf_counter()

    facet_texts = [f["text"] for f in JD_FACETS]
    facet_embeddings = model.encode(
        facet_texts,
        batch_size=12,
        show_progress_bar=False,
        convert_to_numpy=True,
    ).astype(np.float32)

    print(f"  Facet embeddings shape: {facet_embeddings.shape}  "
          f"({time.perf_counter() - t0:.2f}s)")

    # ── 5a. Write candidate_embeddings.parquet ────────────────────────
    print("\n" + "=" * 60)
    print("  Writing candidate_embeddings.parquet")
    print("=" * 60)
    t0 = time.perf_counter()

    parquet_path = os.path.join(args.out_dir, "candidate_embeddings.parquet")

    # Build a PyArrow table with candidate_id (string) and
    # embedding (fixed_size_list of float32, length 384).
    id_array = pa.array(candidate_ids, type=pa.string())

    # Convert each row of the numpy matrix into a Python list so
    # PyArrow can wrap it as a fixed-size list column.
    emb_lists = [row.tolist() for row in embedding_matrix]
    emb_array = pa.FixedSizeListArray.from_arrays(
        pa.array(np.asarray(emb_lists).flatten(), type=pa.float32()),
        list_size=384,
    )

    table = pa.table({
        "candidate_id": id_array,
        "embedding": emb_array,
    })
    pq.write_table(table, parquet_path)

    print(f"  Written {parquet_path} in {time.perf_counter() - t0:.1f}s")
    print(f"  File size: {os.path.getsize(parquet_path) / 1e6:.1f} MB")

    # Verify: re-read and spot-check
    verify_table = pq.read_table(parquet_path)
    assert verify_table.num_rows == n_candidates, (
        f"Row count mismatch: expected {n_candidates}, got {verify_table.num_rows}"
    )
    sample_emb = verify_table.column("embedding")[0].as_py()
    assert len(sample_emb) == 384, (
        f"Embedding length mismatch: expected 384, got {len(sample_emb)}"
    )
    print(f"  Verified: {verify_table.num_rows:,} rows, "
          f"embedding length = {len(sample_emb)}")

    # ── 5b. Write jd_facet_embeddings.npy ─────────────────────────────
    print("\n" + "=" * 60)
    print("  Writing jd_facet_embeddings.npy")
    print("=" * 60)

    npy_path = os.path.join(args.out_dir, "jd_facet_embeddings.npy")
    np.save(npy_path, facet_embeddings)

    # Verify
    loaded = np.load(npy_path)
    assert loaded.shape == (12, 384), f"Shape mismatch: {loaded.shape}"
    assert loaded.dtype == np.float32, f"Dtype mismatch: {loaded.dtype}"
    print(f"  Written {npy_path}")
    print(f"  Shape: {loaded.shape}, dtype: {loaded.dtype}")
    print(f"  File size: {os.path.getsize(npy_path) / 1e3:.1f} KB")

    # ── 5c. Write jd_facet_metadata.json ──────────────────────────────
    print("\n" + "=" * 60)
    print("  Writing jd_facet_metadata.json")
    print("=" * 60)

    json_path = os.path.join(args.out_dir, "jd_facet_metadata.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(JD_FACETS, f, indent=2, ensure_ascii=False)

    print(f"  Written {json_path}")
    print(f"  {len(JD_FACETS)} facets: "
          f"{sum(1 for d in JD_FACETS if d['tier']=='core')} core, "
          f"{sum(1 for d in JD_FACETS if d['tier']=='bonus')} bonus, "
          f"{sum(1 for d in JD_FACETS if d['tier']=='penalty')} penalty")

    # ── Summary ───────────────────────────────────────────────────────
    total_time = time.perf_counter() - t_global
    print("\n" + "=" * 60)
    print("  PRECOMPUTE COMPLETE")
    print("=" * 60)
    print(f"  Candidates embedded : {n_candidates:,}")
    print(f"  JD facets embedded  : {facet_embeddings.shape[0]}")
    print(f"  Total runtime       : {total_time:.1f}s ({total_time/60:.1f} min)")
    print()
    print("  Output files:")
    for p in [parquet_path, npy_path, json_path]:
        sz = os.path.getsize(p)
        unit = "MB" if sz > 1e6 else "KB"
        val = sz / 1e6 if sz > 1e6 else sz / 1e3
        print(f"    {os.path.basename(p):40s} {val:8.1f} {unit}")
    print("=" * 60)


if __name__ == "__main__":
    main()
