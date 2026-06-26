# Assay — AI-Powered Candidate Ranking Pipeline

> **Hackathon Submission** — India Runs Data & AI Challenge · Redrob Track
> Rank 100,000 candidates for a Search/ML Engineer role using intelligent, explainable AI.

---

## Overview

Assay is a two-stage, CPU-only candidate ranking pipeline that processes 100K+ candidate profiles and produces a ranked Top-100 list with plain-language recruiter reasoning. Designed to be **merit-first, explainable, and anti-gaming**.

### Key Differentiators

| Feature | What we do | Why it matters |
|---|---|---|
| **12 JD Facet Alignment** | Semantic cosine similarity across 4 core, 5 bonus, 3 penalty facets | Goes beyond keyword matching |
| **Verified Skill Multiplier** | Platform assessment scores (0–100) scale candidate scores by [0.50, 1.20] | Credentials verified, not self-reported |
| **Anti-Keyword-Stuffing** | 4-layer defense: co-occurrence + metric verification + density cap + assessment cross-check | Prevents gaming the system |
| **Continuous Notice Period Curve** | Piecewise linear: 1.0 (≤30d) → 0.80 floor (≥120d) | Merit-first; notice is a soft signal |
| **Product Company Detection** | Tenure-weighted product vs. consulting ratio: +15% / −20% | Rewards real product depth |
| **Factual Reasoning Engine** | 80–160 char recruiter summaries from structured data | Zero hallucination, fully deterministic |

---

## Pipeline Architecture

```
candidates.jsonl (100K profiles)
         │
         ▼
 ┌───────────────────────┐
 │  Stage 1 — rank.py    │  DuckDB SQL pre-filter
 │  Location + Role      │  ~45 seconds
 │  → survivors.csv      │  ~25K candidates
 └──────────┬────────────┘
            │
            ▼
 ┌───────────────────────┐
 │  Stage 2              │  score_and_rank.py
 │  score_and_rank.py    │  ~90 seconds
 │                       │
 │  1. Honeypot purge    │
 │  2. Vector alignment  │  12 JD facets
 │  3. Skill multiplier  │  verified scores
 │  4. Behavioral gates  │
 │  5. Product co. boost │
 │  6. Tier + sort       │
 │  7. Reasoning export  │
 │                       │
 │  → submission.csv     │  Top 100
 └───────────────────────┘
```

**Total runtime: < 3 minutes · Peak RAM: ~4 GB · CPU-only · No network**

---

## Scoring Formula

```
core_score = GeometricMean(4 core cosine similarities) × verified_skill_multiplier

base_fit   = 0.70 × core_score
           + 0.20 × bonus_score
           − 0.30 × penalty_score
           + 0.05 × college_tier
           + 0.05 × cgpa_norm

base_fit   = base_fit × product_company_multiplier + shipped_search_boost

final_score = base_fit × sqrt(availability_multiplier) × conversion_drag + location_boost
```

---

## Project Structure

```
Assay/
├── precompute_embeddings.py   # One-time: encode all profiles + JD facets
├── rank.py                    # Stage 1 (root copy)
├── score_and_rank.py          # Stage 2 (root copy)
├── jd_facet_metadata.json     # 12 JD facet definitions
├── requirements.txt
├── submission_metadata.yaml
├── README.md
└── v2/
    ├── rank.py                # Stage 1 — competition version
    ├── score_and_rank.py      # Stage 2 — competition version
    ├── submission.csv         # Final Top-100 output
    └── hackathon_submission.pptx
```

> Large data files are excluded from the repo:
> `candidates.jsonl` (~487 MB), `candidate_embeddings.parquet` (~148 MB), `survivors.csv` (~93 MB)

---

## Setup & Usage

### 1. Install dependencies

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Precompute embeddings *(one-time, ~10 min)*

```bash
python precompute_embeddings.py \
  --candidates candidates.jsonl \
  --out-parquet candidate_embeddings.parquet \
  --out-facets-npy jd_facet_embeddings.npy \
  --out-facets-meta jd_facet_metadata.json
```

### 3. Stage 1 — Pre-filter

```bash
python v2/rank.py \
  --candidates candidates.jsonl \
  --out v2/survivors.csv
```

### 4. Stage 2 — Score & rank

```bash
python v2/score_and_rank.py \
  --survivors v2/survivors.csv \
  --embeddings candidate_embeddings.parquet \
  --facets-npy jd_facet_embeddings.npy \
  --facets-meta jd_facet_metadata.json \
  --candidates candidates.jsonl \
  --out v2/submission.csv
```

---

## Top 10 Results

| Rank | Candidate ID | Score | Company | YoE | Location |
|------|-------------|------:|---------|----:|----------|
| 1 | CAND_0041669 | 1.0000 | CRED | 8.0y | Noida |
| 2 | CAND_0064326 | 0.7235 | Sarvam AI | 7.6y | Gurgaon |
| 3 | CAND_0006418 | 0.7160 | Verloop.io | 5.7y | Gurgaon |
| 4 | CAND_0054394 | 0.6927 | PharmEasy | 4.1y | Pune |
| 5 | CAND_0096142 | 0.6859 | upGrad | 5.0y | Hyderabad |
| 6 | CAND_0018499 | 0.6417 | Zomato | 7.2y | Noida |
| 7 | CAND_0043381 | 0.6342 | PharmEasy | 3.6y | Pune |
| 8 | CAND_0099806 | 0.6119 | Mad Street Den | 4.6y | Bhubaneswar |
| 9 | CAND_0041610 | 0.6021 | Zoho | 6.7y | Indore |
| 10 | CAND_0052328 | 0.5892 | Amazon | 6.5y | Pune |

---

## Technologies

| Library | Version | Purpose |
|---|---|---|
| Python | 3.11 | Core pipeline |
| DuckDB | 1.5.3 | SQL streaming over JSONL with nested struct queries |
| NumPy | 2.4.6 | Vectorized cosine similarity matrix |
| Pandas | 3.0.3 | DataFrame orchestration and tiered sorting |
| sentence-transformers | 5.5.1 | `all-MiniLM-L6-v2` — profile + JD facet embeddings |
| pyarrow | 24.0.0 | Parquet I/O for pre-computed embeddings |

---

## Design Decisions

### Why geometric mean for core score?
Arithmetic mean lets a candidate compensate a weak facet by excelling in another. Geometric mean enforces *balanced* competency — a 0.9/0.9/0.9/0.1 profile scores 0.53 (geometric) vs 0.70 (arithmetic). The JD requires all four core skills, not three.

### Why a continuous notice period curve instead of a hard cutoff?
A binary cutoff treats a 59-day and 61-day notice candidate as entirely different. A piecewise linear curve from 1.0 (≤30d) to a 0.80 floor (≥120d) smoothly penalises longer notice while never eliminating an otherwise exceptional candidate.

### Why 4-layer anti-stuffing?
Each layer closes a different attack vector independently: sentence co-occurrence (claims must have context), metric verification (numbers must appear near claims), density cap (frequency ceiling per skill), and assessment cross-check (platform score must corroborate self-reported expertise).

---

## Constraints Compliance

| Constraint | Requirement | Result |
|---|---|---|
| Runtime | < 5 minutes | ~2.5 min ✓ |
| RAM | < 16 GB | ~4 GB peak ✓ |
| Compute | CPU only | Zero GPU ✓ |
| Network | No access | Fully offline ✓ |
| Output | 100 ranked candidates | Exactly 100 ✓ |
| Reasoning length | 80–160 characters | All compliant ✓ |
| Honeypots in Top 100 | 0 | 0 ✓ |
