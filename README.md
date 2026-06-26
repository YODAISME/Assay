# ApexRank — AI-Powered Candidate Ranking Pipeline

> **Hackathon Submission** — India Runs Data & AI Challenge · Redrob Track
> **Problem Statement**: Rank 100,000 candidates for a Search/ML Engineer role using intelligent, explainable AI.

---

## Overview

ApexRank is a two-stage, CPU-only candidate ranking pipeline that processes 100K+ candidate profiles from a JSONL dataset and produces a ranked Top-100 list with plain-language recruiter reasoning. It is designed to be **merit-first, explainable, and anti-gaming**.

### Key Differentiators

| Feature | What we do | Why it matters |
|---|---|---|
| **12 JD Facet Alignment** | Semantic cosine similarity across 4 core, 5 bonus, and 3 penalty facets | Goes beyond keyword matching |
| **Verified Skill Multiplier** | Platform assessment scores (0-100) scale candidate scores by [0.50, 1.20] | Credentials verified, not self-reported |
| **Anti-Keyword-Stuffing (4-Layer)** | Sentence co-occurrence + metric verification + density cap + assessment cross-check | Prevents gaming the system |
| **Continuous Notice Period Curve** | Piecewise linear suitability: 1.0 (<=30d) to 0.80 floor (>=120d) | Merit-first, notice is a soft signal |
| **Product Company Detection** | Tenure-weighted product vs. consulting ratio: +15% / -20% | Rewards real product depth |
| **Factual Reasoning Engine** | 80-160 char recruiter summaries composed from structured data | Zero hallucination, fully deterministic |

---

## Pipeline Architecture

`
candidates.jsonl (100K profiles)
        |
        v
+----------------------------------+
|  STAGE 1: Pre-Filtering          |  rank.py (~45 seconds)
|  DuckDB SQL - Location + Role    |
|  Output: survivors.csv (~25K)    |
+----------------+-----------------+
                 |
                 v
+----------------------------------+
|  STAGE 2: Scoring & Ranking      |  score_and_rank.py (~90 seconds)
|                                  |
|  1. Honeypot Purge               |
|  2. Vector Alignment (12 facets) |
|  3. Verified Skill Multiplier    |
|  4. Behavioral Gating            |
|  5. Product Co. Multiplier       |
|  6. Tier Assignment + Sorting    |
|  7. Reasoning + Export           |
|                                  |
|  Output: submission.csv (Top 100)|
+----------------------------------+
`

**Total runtime: < 3 minutes | Peak RAM: ~4 GB | CPU-only | No network**

---

## Scoring Formula

`
core_score  = GeometricMean(4 core cosine similarities) x verified_skill_multiplier

base_fit    = 0.7 x core_score
            + 0.2 x bonus_score
            - 0.3 x penalty_score
            + 0.05 x college_tier
            + 0.05 x cgpa_norm

base_fit    = base_fit x product_company_multiplier + shipped_search_boost

final_score = base_fit x sqrt(availability_multiplier) x conversion_drag + location_boost
`

---

## Project Structure

`
apexrank/
|
+-- precompute_embeddings.py   # Offline: encode all profiles + JD facets
+-- v2/
|   +-- rank.py                # Stage 1: SQL pre-filtering via DuckDB
|   +-- score_and_rank.py      # Stage 2: vectorized multi-signal scoring
|
+-- jd_facet_metadata.json     # 12 JD facet definitions (4 core, 5 bonus, 3 penalty)
+-- requirements.txt
+-- submission_metadata.yaml
+-- README.md
`

**Not included in repo** (large data files):
- candidates.jsonl - 100K candidate dataset (~487 MB)
- candidate_embeddings.parquet - Pre-computed embeddings (~148 MB)
- survivors.csv - Stage 1 output (~93 MB)

---

## Setup & Usage

### 1. Install Dependencies

`ash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
`

### 2. Precompute Embeddings (one-time, ~10 min)

`ash
python precompute_embeddings.py --candidates candidates.jsonl --out-parquet candidate_embeddings.parquet --out-facets-npy jd_facet_embeddings.npy --out-facets-meta jd_facet_metadata.json
`

### 3. Stage 1 - Pre-Filter

`ash
python v2/rank.py --candidates candidates.jsonl --out v2/survivors.csv
`

### 4. Stage 2 - Score & Rank

`ash
python v2/score_and_rank.py --survivors v2/survivors.csv --embeddings candidate_embeddings.parquet --facets-npy jd_facet_embeddings.npy --facets-meta jd_facet_metadata.json --candidates candidates.jsonl --out v2/submission.csv
`

---

## Top 10 Results

| Rank | Candidate ID | Score | Company | YoE | Location |
|------|-------------|-------|---------|-----|----------|
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
| DuckDB | 1.3.x | SQL streaming of JSONL, nested struct queries |
| NumPy | 2.2.x | Vectorized cosine similarity matrix |
| Pandas | 2.3.x | DataFrame orchestration |
| sentence-transformers | 4.1.x | all-MiniLM-L6-v2 profile embeddings |
| pyarrow | 20.x | Parquet I/O |

---

## Design Decisions

### Why Geometric Mean over Arithmetic Mean for Core Score?
Arithmetic mean allows a candidate to rescue their score by excelling in one facet while being weak in others. Geometric mean forces *balanced* competency across all 4 core facets. A candidate who scores 0.9/0.9/0.9/0.1 gets a geometric mean of 0.53 instead of an arithmetic 0.70.

### Why a continuous Notice Period curve instead of a hard cutoff?
Hard cutoffs create brittleness. A continuous piecewise linear curve from 1.0 (<=30 days) to a 0.80 floor (>=120 days) smoothly penalizes longer notice while ensuring it never completely eliminates an otherwise exceptional candidate.

### Why 4-layer anti-stuffing defense?
Keyword matching is trivially gameable. The 4 layers (sentence co-occurrence, metric verification, keyword density cap, assessment cross-check) each independently close a different attack vector.

---

## Constraints Compliance

| Constraint | Requirement | Achieved |
|---|---|---|
| Runtime | < 5 minutes | ~2.5 minutes total |
| RAM | < 16 GB | ~4 GB peak |
| Compute | CPU only | Zero GPU |
| Network | No access | Fully offline |
| Output | 100 ranked candidates | Exactly 100 |
| Reasoning | 80-160 characters | All compliant |
| Honeypots | 0 in Top 100 | Verified |
