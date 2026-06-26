"""
score_and_rank.py -- Hackathon Candidate-Ranking Pipeline (Stage 2)
==================================================================
Optimized candidate scoring stack featuring vectorized alignment layers, Log-Clipped 
Geometric Mean calculations, verified skill assessment modifiers, continuous notice period 
suitability curves, product company experience boosts, and target location preferences.

Constraints: <5 min, <16 GB RAM, CPU only, no network.
"""

import argparse
import json
import re
import time
from datetime import datetime

import duckdb
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Core Vectorized Helpers
# ---------------------------------------------------------------------------

def timer(label: str):
    class _Timer:
        def __enter__(self):
            self.t0 = time.perf_counter()
            print(f"\n{'='*60}\n  STEP: {label}\n{'='*60}")
            return self
        def __exit__(self, *_):
            print(f"  [OK] {label} completed in {time.perf_counter() - self.t0:.2f}s")
    return _Timer()


def trapezoidal_experience_fit(years_series: pd.Series) -> np.ndarray:
    """Vectorized calculation of experience milestones using NumPy conditions."""
    y = years_series.fillna(0.0).values
    fit = np.zeros_like(y, dtype=np.float32)
    
    m1 = (y >= 0) & (y < 3)
    fit[m1] = (0.5 / 3.0) * y[m1]
    
    m2 = (y >= 3) & (y < 5)
    fit[m2] = 0.5 + (0.5 / 2.0) * (y[m2] - 3.0)
    
    m3 = (y >= 5) & (y <= 9)
    fit[m3] = 1.0
    
    m4 = (y > 9) & (y <= 12)
    fit[m4] = 1.0 - (0.5 / 3.0) * (y[m4] - 9.0)
    
    m5 = (y > 12) & (y <= 16)
    fit[m5] = 0.5 - (0.5 / 4.0) * (y[m5] - 12.0)
    
    return fit


def parse_cgpa(val) -> float or None:
    import re
    if pd.isna(val) or val is None:
        return None
    s = str(val).strip().upper()
    m = re.search(r'([0-9.]+)', s)
    if m:
        try:
            num = float(m.group(1))
            return num / 10.0 if ('%' in s or num > 10.0) else num
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------
# Priority 1: Verified Skill Assessment Classifications & Helpers
# ---------------------------------------------------------------------------

CORE_SEARCH_SKILLS = {
    'Information Retrieval', 'RAG', 'Vector Search', 'Semantic Search',
    'Recommendation Systems', 'Learning to Rank', 'Pinecone', 'Milvus',
    'Qdrant', 'Weaviate', 'pgvector', 'FAISS', 'Elasticsearch', 'OpenSearch'
}

ML_FRAMEWORKS_SKILLS = {
    'Python', 'Machine Learning', 'Deep Learning', 'PyTorch', 'TensorFlow',
    'scikit-learn', 'Sentence Transformers', 'Hugging Face Transformers',
    'LLMs', 'Prompt Engineering', 'Fine-tuning LLMs', 'LoRA', 'QLoRA',
    'PEFT', 'LangChain', 'LlamaIndex', 'Haystack'
}

CV_SPEECH_ROBOTICS_SKILLS = {
    'YOLO', 'CNN', 'OpenCV', 'Object Detection', 'Computer Vision',
    'Image Classification', 'Speech Recognition', 'TTS', 'ASR',
    'Diffusion Models', 'GANs'
}

def compute_skill_multiplier(row) -> float:
    scores_str = row.get("skill_assessment_scores")
    if pd.isna(scores_str) or not scores_str:
        return 1.0
    
    try:
        scores = json.loads(scores_str)
    except Exception:
        return 1.0
        
    boost = 0.0
    drag = 1.0
    
    for skill, score in scores.items():
        if score is None:
            continue
        
        # Classify skill weight
        if skill in CORE_SEARCH_SKILLS:
            weight = 1.0
        elif skill in ML_FRAMEWORKS_SKILLS:
            weight = 0.5
        else:
            weight = 0.0
            
        if weight > 0:
            if score >= 70:
                boost += weight * ((score - 70) / 30.0) * 0.10  # Max 10% boost per skill
            elif score < 50:
                drag *= (1.0 - weight * ((50 - score) / 50.0) * 0.20)  # Max 20% drag per skill
                
    boost = min(boost, 0.20)  # Cap boost at 20%
    drag = max(drag, 0.50)   # Floor drag at 50%
    
    return (1.0 + boost) * drag


# ---------------------------------------------------------------------------
# Priority 2: Continuous Notice Period Curve
# ---------------------------------------------------------------------------

def compute_notice_period_multiplier(notice_days_series: pd.Series) -> np.ndarray:
    n = notice_days_series.fillna(30.0).values
    mult = np.ones_like(n, dtype=np.float32)
    
    # 0 to 30 days: 1.0
    # 30 to 60 days: 1.0 to 0.95
    m1 = (n > 30) & (n <= 60)
    mult[m1] = 1.0 - (0.05 / 30.0) * (n[m1] - 30.0)
    
    # 60 to 90 days: 0.95 to 0.88
    m2 = (n > 60) & (n <= 90)
    mult[m2] = 0.95 - (0.07 / 30.0) * (n[m2] - 60.0)
    
    # 90 to 120 days: 0.88 to 0.82
    m3 = (n > 90) & (n <= 120)
    mult[m3] = 0.88 - (0.06 / 30.0) * (n[m3] - 90.0)
    
    # 120+ days: 0.82 to 0.80 (capped at 0.80)
    m4 = (n > 120)
    mult[m4] = np.maximum(0.80, 0.82 - (0.02 / 60.0) * (n[m4] - 120.0))
    
    return mult


# ---------------------------------------------------------------------------
# Priority 3: Location Boost
# ---------------------------------------------------------------------------

def compute_location_boost(location_series: pd.Series) -> np.ndarray:
    locs = location_series.fillna("").str.lower().str.strip().values
    boost = np.zeros_like(locs, dtype=np.float32)
    
    pune_mask = np.array([loc.startswith("pune") for loc in locs])
    noida_mask = np.array([loc.startswith("noida") for loc in locs])
    boost[pune_mask | noida_mask] = 0.015
    
    sec_cities = ["hyderabad", "gurgaon", "delhi", "mumbai"]
    for city in sec_cities:
        city_mask = np.array([loc.startswith(city) for loc in locs])
        boost[city_mask & ~pune_mask & ~noida_mask] = 0.005
        
    return boost


# ---------------------------------------------------------------------------
# Priority 5: Product Company Detection & Career Keywords
# ---------------------------------------------------------------------------

PRODUCT_COMPANIES = {
    'google', 'amazon', 'meta', 'netflix', 'apple', 'linkedin', 'salesforce', 'adobe',
    'cred', 'swiggy', 'zomato', 'flipkart', 'razorpay', 'inmobi', 'upgrad', 'unacademy',
    'vedantu', 'pharmeasy', 'ola', 'nykaa', 'meesho', 'dream11', 'freshworks', 'zoho',
    'paytm', 'phonepe', 'policybazaar', 'byju\'s', 'glance',
    'aganitha', 'krutrim', 'locobuzz', 'mad street den', 'observe.ai', 'rephrase.ai',
    'saarthi.ai', 'sarvam ai', 'verloop.io', 'wysa', 'yellow.ai', 'haptik', 'niramai',
    'pied piper', 'hooli', 'initech'
}

CONSULTING_COMPANIES = {
    'tcs', 'wipro', 'infosys', 'hcl', 'cognizant', 'accenture', 'capgemini',
    'tech mahindra', 'mindtree', 'mphasis', 'genpact ai'
}

SEARCH_KEYWORDS = [
    'search', 'retrieval', 'ranking', 'recommendation', 'recommender', 'ir', 
    'dense retrieval', 'hybrid search', 'rag', 'pinecone', 'milvus', 'qdrant', 
    'weaviate', 'elasticsearch', 'opensearch', 'vector search', 'semantic search'
]
PRODUCTION_KEYWORDS = [
    'deploy', 'production', 'scale', 'real user', 'shipped', 'served', 
    'latency', 'pipeline', 'ab test', 'a/b test'
]
METRIC_INDICATORS = [
    '%', 'percent', 'million', 'users', 'qps', 'ms', 'latency', 'ctr', 
    'conversion', 'ndcg', 'mrr', 'map', 'accuracy', 'precision', 'recall'
]

ALL_TECH_KEYWORDS = [
    'rag', 'pinecone', 'milvus', 'qdrant', 'weaviate', 'elasticsearch', 'opensearch',
    'faiss', 'pgvector', 'langchain', 'llamaindex', 'haystack', 'lora', 'qlora', 'peft',
    'pytorch', 'tensorflow', 'scikit-learn', 'xgboost', 'spacy', 'nltk', 'bert', 'gpt',
    'llm', 'sentence transformers', 'hugging face'
]

def compute_product_company_multiplier(row) -> float:
    companies = row.get("career_companies")
    durations = row.get("career_durations")
    
    if companies is None or durations is None:
        return 1.0
        
    prod_dur = 0.0
    cons_dur = 0.0
    
    for comp, dur in zip(companies, durations):
        if pd.isna(comp) or pd.isna(dur):
            continue
        c_clean = str(comp).lower().strip()
        d_val = float(dur)
        
        if c_clean in PRODUCT_COMPANIES:
            prod_dur += d_val
        elif c_clean in CONSULTING_COMPANIES:
            cons_dur += d_val
            
    prod_factor = min(1.0, prod_dur / 48.0)
    cons_factor = min(1.0, cons_dur / 48.0)
    
    return 1.0 + 0.15 * prod_factor - 0.20 * cons_factor


def check_shipped_search_system(row) -> bool:
    descriptions = row.get("career_descriptions")
    scores_str = row.get("skill_assessment_scores")
    
    if descriptions is None:
        return False
        
    # Defense 4: Check if they failed Python/Search assessments
    if pd.notna(scores_str) and scores_str:
        try:
            scores = json.loads(scores_str)
            for s_name, s_val in scores.items():
                s_name_lower = s_name.lower()
                if ('python' in s_name_lower or 'rag' in s_name_lower or 'search' in s_name_lower) and s_val < 45:
                    return False
        except Exception:
            pass
            
    for desc in descriptions:
        if pd.isna(desc) or not desc:
            continue
            
        desc_lower = str(desc).lower()
        
        # Defense 3: Keyword Density Capping
        tech_hits = sum(1 for kw in ALL_TECH_KEYWORDS if kw in desc_lower)
        if tech_hits > 8:
            continue  # Exclude keyword stuffed descriptions
            
        # Split description into sentences
        sentences = re.split(r'[.!?\n]+', desc_lower)
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
                
            # Check for Search + Production keyword co-occurrence (Defense 1)
            has_search = any(kw in sentence for kw in SEARCH_KEYWORDS)
            has_prod = any(kw in sentence for kw in PRODUCTION_KEYWORDS)
            
            if has_search and has_prod:
                # Defense 2: Metric/Numeric verification
                has_number = bool(re.search(r'\d+', sentence))
                has_metric = any(kw in sentence for kw in METRIC_INDICATORS)
                
                if has_number or has_metric:
                    return True
                    
    return False


# ---------------------------------------------------------------------------
# Semantic Maps and Rubric-Compliant Reasoning Engine
# ---------------------------------------------------------------------------

FACET_SHORT_MAP = {
    "retrieval_systems": "embeddings retrieval",
    "vector_db_search": "vector DB search",
    "python_engineering": "Python ML engineering",
    "ranking_evaluation": "ranking evaluation",
    "learning_to_rank": "learning-to-rank",
    "llm_finetuning": "LLM fine-tuning",
    "hr_recruiting_marketplace": "HR/marketplace search",
    "distributed_systems": "distributed systems",
    "open_source": "open-source ML",
}


def _short_location(location: str) -> str:
    loc = (location or "").strip()
    if not loc or loc.lower() == "unknown":
        return ""
    return loc.split(",")[0].strip()


def _short_title(title: str, max_len: int = 26) -> str:
    title = (title or "Engineer").strip()
    if len(title) <= max_len:
        return title
    return title[: max_len - 3].rstrip() + "..."


def _primary_facet(facet_similarities, facet_metadata) -> str:
    core_labels = [m["label"] for m in facet_metadata if m["tier"] == "core"]
    bonus_labels = [m["label"] for m in facet_metadata if m["tier"] == "bonus"]
    best_core = max(core_labels, key=lambda label: facet_similarities.get(label, 0))
    if facet_similarities.get(best_core, 0) >= 0.25:
        facet_label = best_core
    else:
        facet_label = max(bonus_labels, key=lambda label: facet_similarities.get(label, 0))
    return FACET_SHORT_MAP.get(facet_label, "search infrastructure")


def _profile_concerns(row) -> list[str]:
    concerns = []
    if bool(row.get("title_chasing_flag", False)):
        concerns.append("short tenures")
    if float(row.get("experience_band_fit", 1.0)) < 0.5:
        concerns.append("limited depth")
    np_days = row.get("notice_period")
    if pd.notna(np_days) and np_days > 60:
        concerns.append(f"{int(np_days)}-day notice")
    if float(row.get("penalty_score", 0.0)) > 0.30:
        concerns.append("domain drift")
    return concerns


def _clamp_reasoning(text: str, min_len: int = 80, max_len: int = 160) -> str:
    text = " ".join(text.split())
    if len(text) > max_len:
        text = text[: max_len - 3].rstrip(" ,;:-") + "..."
    if len(text) < min_len:
        text = f"{text} Meets baseline search-engineering fit."
    if len(text) > max_len:
        text = text[: max_len - 3].rstrip(" ,;:-") + "..."
    return text


def generate_reasoning(row, facet_similarities, facet_metadata):
    """
    Plain-language recruiter summaries with rank-consistent tone.
    Text is composed within the 80-160 character band from the start.
    """
    rank = int(row["rank"])
    yoe = float(row["total_exp_years"] or 0)
    title = _short_title(str(row.get("current_title") or "Engineer"))
    company = str(row.get("current_company") or "").strip()
    city = _short_location(str(row.get("location") or ""))
    facet = _primary_facet(facet_similarities, facet_metadata)
    concerns = _profile_concerns(row)

    company_bit = f" at {company}" if company and company.lower() != "unknown" else ""
    loc_bit = f", {city}" if city else ""
    concern_bit = f"; note {concerns[0]}" if concerns else ""

    if rank <= 20:
        if concerns:
            reasoning = (
                f"Top-tier {title}{company_bit}: {yoe:.1f}y in {facet}{loc_bit}{concern_bit}, "
                f"but strong product search fit."
            )
        else:
            reasoning = (
                f"Excellent {title}{company_bit}: {yoe:.1f}y delivering {facet}{loc_bit}; "
                f"clear top match for this search role."
            )
    elif rank <= 70:
        if concerns:
            reasoning = (
                f"Competent {title}{company_bit}: {yoe:.1f}y in {facet}{loc_bit}{concern_bit}; "
                f"solid mid-list trade-off."
            )
        else:
            reasoning = (
                f"Competent {title}{company_bit}: {yoe:.1f}y applied {facet} work{loc_bit}; "
                f"steady timeline and good availability."
            )
    elif concerns:
        reasoning = (
            f"Below cutoff — adjacent {facet} fit only; {yoe:.1f}y as {title}{loc_bit}; "
            f"gaps: {', '.join(concerns[:2])}."
        )
    else:
        reasoning = (
            f"Below cutoff filler — partial {facet} overlap; {yoe:.1f}y {title}{company_bit}{loc_bit}; "
            f"included for baseline coverage."
        )

    return _clamp_reasoning(reasoning)


# ---------------------------------------------------------------------------
# Pipeline Execution
# ---------------------------------------------------------------------------

def main():
    t_global = time.perf_counter()
    parser = argparse.ArgumentParser()
    parser.add_argument("--survivors", required=True)
    parser.add_argument("--embeddings", required=True)
    parser.add_argument("--facets-npy", required=True)
    parser.add_argument("--facets-meta", required=True)
    parser.add_argument("--candidates", default="candidates.jsonl")
    parser.add_argument("--out", default="final_submission.csv")
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # LOAD AND ENRICH DATA (VECTORIZED DATA ENRICHMENT LAYER)
    # ------------------------------------------------------------------
    with timer("Load inputs & Dynamic SQL Aggregation"):
        survivors = pd.read_csv(args.survivors)
        facet_embeddings = np.load(args.facets_npy).astype(np.float32)
        with open(args.facets_meta, "r", encoding="utf-8") as f:
            facet_metadata = json.load(f)

        core_idx    = [i for i, m in enumerate(facet_metadata) if m["tier"] == "core"]
        bonus_idx   = [i for i, m in enumerate(facet_metadata) if m["tier"] == "bonus"]
        penalty_idx = [i for i, m in enumerate(facet_metadata) if m["tier"] == "penalty"]

        con = duckdb.connect(database=":memory:")
        con.register("survivors_view", survivors)
        
        emb_df = con.execute(f"SELECT candidate_id, embedding FROM read_parquet('{args.embeddings}') WHERE candidate_id IN (SELECT candidate_id FROM survivors_view)").df()
        
        # Enriched column schema matching candidate_schema.json properties
        SCHEMA_COLUMNS = {
            'candidate_id': 'VARCHAR',
            'profile': 'STRUCT(current_industry VARCHAR, location VARCHAR)',
            'skills': 'STRUCT(name VARCHAR, proficiency VARCHAR, duration_months INT)[]',
            'career_history': 'STRUCT(company VARCHAR, title VARCHAR, duration_months INT, industry VARCHAR, company_size VARCHAR, description VARCHAR)[]',
            'education': 'STRUCT(tier VARCHAR, grade VARCHAR)[]',
            'redrob_signals': 'STRUCT(last_active_date VARCHAR, open_to_work_flag BOOLEAN, profile_views_received_30d INT, recruiter_response_rate DOUBLE, saved_by_recruiters_30d INT, interview_completion_rate DOUBLE, offer_acceptance_rate DOUBLE, github_activity_score DOUBLE, notice_period_days INT, skill_assessment_scores VARCHAR)'
        }
        
        extra_df = con.execute(f"""
            SELECT 
                s.candidate_id,
                -- Step 1 Honeypot Metrics
                COALESCE(list_aggr(list_transform(c.career_history, x -> x.duration_months), 'sum'), 0) AS career_duration_sum,
                COALESCE(list_aggr(list_transform(c.skills, x -> CASE WHEN lower(x.proficiency) = 'expert' AND x.duration_months < 12 THEN 1 ELSE 0 END), 'sum'), 0) AS n_expert_low_dur,
                
                -- Step 3 Structural Metrics
                COALESCE(list_aggr(list_transform(c.career_history, x -> x.duration_months), 'avg'), 0.0) AS avg_tenure_months,
                CASE 
                    WHEN COALESCE(list_min(list_transform(c.career_history, x -> 
                        CASE 
                            WHEN trim(x.company_size) IN ('1-9', '1-10', '1-5') THEN 1
                            WHEN trim(x.company_size) IN ('10-50', '11-50') THEN 2
                            WHEN trim(x.company_size) IN ('51-200') THEN 3
                            WHEN trim(x.company_size) IN ('201-500') THEN 4
                            WHEN trim(x.company_size) IN ('501-1000') THEN 5
                            WHEN trim(x.company_size) IN ('1001-5000') THEN 6
                            WHEN trim(x.company_size) IN ('5001-10000') THEN 7
                            WHEN trim(x.company_size) IN ('10001+', '10,001+') THEN 8
                            ELSE 8
                        END
                    )), 8) <= 2 THEN 1.0 
                    ELSE 0.0 
                END AS startup_exposure_flag,
                
                -- Recruiter, Profile & Factual Signal Extraction
                c.profile.current_industry AS current_industry,
                c.profile.location AS location,
                c.redrob_signals.notice_period_days AS notice_period,
                c.redrob_signals.saved_by_recruiters_30d AS saved_by_recruiters_30d,
                c.redrob_signals.profile_views_received_30d AS profile_views_received_30d,
                c.redrob_signals.github_activity_score AS github_score,
                c.redrob_signals.recruiter_response_rate AS response_rate,
                c.redrob_signals.last_active_date AS last_active,
                c.redrob_signals.open_to_work_flag AS open_to_work,
                c.redrob_signals.interview_completion_rate AS interview_completion_rate,
                c.redrob_signals.offer_acceptance_rate AS offer_acceptance_rate,
                c.education[1].tier AS college_tier,
                c.education[1].grade AS raw_grade,
                
                -- Nesting lists for custom career history & skill score processing in Python
                c.redrob_signals.skill_assessment_scores AS skill_assessment_scores,
                list_transform(c.career_history, x -> x.company) AS career_companies,
                list_transform(c.career_history, x -> x.duration_months) AS career_durations,
                list_transform(c.career_history, x -> x.industry) AS career_industries,
                list_transform(c.career_history, x -> x.description) AS career_descriptions
            FROM survivors_view s
            LEFT JOIN read_json_auto('{args.candidates}', columns={SCHEMA_COLUMNS}, format='newline_delimited') c
              ON s.candidate_id = c.candidate_id
        """).df()
        con.close()
        
        cols_to_drop = [col for col in extra_df.columns if col in survivors.columns and col != "candidate_id"]
        candidates = survivors.drop(columns=cols_to_drop).merge(extra_df, on="candidate_id", how="left")
        candidates["cgpa"] = candidates["raw_grade"].apply(parse_cgpa)

    # ------------------------------------------------------------------
    # STEP 1 -- HONEYPOT PURGE (VECTORIZED)
    # ------------------------------------------------------------------
    with timer("Step 1 -- Honeypot Detection"):
        yoe_gap_months = (candidates["total_exp_years"].fillna(0.0).values * 12) - candidates["career_duration_sum"].values
        is_honeypot = (yoe_gap_months > 12) | (candidates["n_expert_low_dur"].values >= 2)
        candidates = candidates[~is_honeypot].copy().reset_index(drop=True)
        print(f"  Purged {is_honeypot.sum():,} profile honeypots.")

    # ------------------------------------------------------------------
    # STEP 2 -- HIGH SPEED VECTOR ALIGNMENT MATRIX & GEOMETRIC CORE
    # ------------------------------------------------------------------
    with timer("Step 2 -- Vector Alignment & Scoring"):
        emb_lookup = emb_df.set_index("candidate_id")["embedding"]
        cand_ids = candidates["candidate_id"].values
        
        aligned_embeddings = emb_lookup.reindex(cand_ids)
        emb_dim = facet_embeddings.shape[1]
        
        cand_emb_matrix = np.vstack([
            np.array(v, dtype=np.float32) if isinstance(v, (list, np.ndarray))
            else np.zeros(emb_dim, dtype=np.float32)
            for v in aligned_embeddings.values
        ])

        cand_norms = np.linalg.norm(cand_emb_matrix, axis=1, keepdims=True)
        cand_emb_normed = cand_emb_matrix / np.where(cand_norms == 0, 1.0, cand_norms)
        
        facet_norms = np.linalg.norm(facet_embeddings, axis=1, keepdims=True)
        facet_emb_normed = facet_embeddings / np.where(facet_norms == 0, 1.0, facet_norms)
        
        sim_matrix = cand_emb_normed @ facet_emb_normed.T

        # Robust, log-clipped Geometric Mean over core criteria
        clipped_core = np.clip(sim_matrix[:, core_idx], 1e-5, 1.0)
        candidates["core_score"] = np.exp(np.log(clipped_core).mean(axis=1))
        
        # Priority 1: Integrate Verified Skill Assessment Scores
        print("  Applying Verified Skill Multiplier...")
        candidates["skill_multiplier"] = candidates.apply(compute_skill_multiplier, axis=1)
        candidates["core_score"] = candidates["core_score"] * candidates["skill_multiplier"]
        
        candidates["bonus_score"]   = sim_matrix[:, bonus_idx].mean(axis=1)
        candidates["penalty_score"] = sim_matrix[:, penalty_idx].mean(axis=1)

        facet_labels = [m["label"] for m in facet_metadata]
        facet_sim_dict = {
            cid: {facet_labels[j]: float(sim_matrix[i, j]) for j in range(len(facet_labels))}
            for i, cid in enumerate(cand_ids)
        }

    # ------------------------------------------------------------------
    # STEP 3 & 4 -- VECTORIZED STRUCTURAL & SOFT AVAILABILITY GATING
    # ------------------------------------------------------------------
    with timer("Step 3 & 4 -- Vectorized Structural & Behavioral Parsing"):
        candidates["title_chasing_flag"] = candidates["avg_tenure_months"] < 18
        candidates["experience_band_fit"] = trapezoidal_experience_fit(candidates["total_exp_years"])

        # Vectorized Availability Multiplier calculation
        TODAY = datetime(2026, 6, 15)
        la_series = pd.to_datetime(candidates["last_active"], errors='coerce')
        days_since = (TODAY - la_series).dt.days.fillna(260).values
        
        recency = np.where(days_since <= 30, 1.0, np.where(days_since >= 260, 0.3, 1.0 - (0.7 / 230.0) * (days_since - 30)))
        resp_rate = candidates["response_rate"].fillna(0.5).values
        otw_bonus = np.where(candidates["open_to_work"].fillna(False), 1.1, 1.0)
        icr = candidates["interview_completion_rate"].fillna(0.5).values
        
        oar_raw = candidates["offer_acceptance_rate"].fillna(-1).values
        oar = np.where(oar_raw < 0, 0.5, oar_raw)

        # Vectorized responsiveness gate execution
        responsiveness_gate = np.where((resp_rate < 0.15) & (recency < 0.4), 0.5, 1.0)
        
        # Priority 2: Continuous Notice Period Curve Score integration
        print("  Applying Continuous Notice Period Multiplier...")
        notice_mult = compute_notice_period_multiplier(candidates["notice_period"])
        
        avail_base = (0.35 * recency + 0.25 * resp_rate + 0.20 * icr + 0.20 * oar)
        candidates["availability_multiplier"] = otw_bonus * avail_base * responsiveness_gate * notice_mult

    # ------------------------------------------------------------------
    # STEP 5 & 6 -- DIRECT ACADEMIC BONUS INJECTION & LEXICOGRAPHICAL RANK
    # ------------------------------------------------------------------
    with timer("Step 5 & 6 -- Academic Integration & Lexicographical Sorting"):
        raw_tiers = candidates["college_tier"].fillna("3").astype(str).str.lower().str.strip().values
        tier_map = {'1': 1.0, 'tier 1': 1.0, 'tier_1': 1.0, '2': 0.5, 'tier 2': 0.5, 'tier_2': 0.5}
        college_norm = np.array([tier_map.get(t, 0.0) for t in raw_tiers])
        
        # Missing grades default cleanly to a neutral 6.0 floor to prevent metric gaming anomalies
        cgpa_norm = np.clip(candidates["cgpa"].fillna(6.0).values / 10.0, 0.0, 1.0)

        # Direct baseline capability mapping step
        candidates["base_fit"] = (
            0.7 * candidates["core_score"]
            + 0.2 * candidates["bonus_score"]
            - 0.3 * candidates["penalty_score"]
            + 0.05 * college_norm  
            + 0.05 * cgpa_norm     
        )

        # Priority 5: Product Company Multiplier & Career Keywords Boost
        print("  Applying Product Company Multipliers & Career Descriptions parsing...")
        candidates["product_mult"] = candidates.apply(compute_product_company_multiplier, axis=1)
        candidates["shipped_search_flag"] = candidates.apply(check_shipped_search_system, axis=1)
        candidates["engineering_boost"] = np.where(candidates["shipped_search_flag"], 0.02, 0.0)
        
        # Inject multiplier + boost
        candidates["base_fit"] = (candidates["base_fit"] * candidates["product_mult"]) + candidates["engineering_boost"]

        # Macro assignments
        candidates["tier"] = 4
        candidates.loc[candidates["base_fit"] >= 0.126, "tier"] = 3
        candidates.loc[(candidates["base_fit"] >= 0.155) & (((candidates["title_chasing_flag"].astype(int) + (candidates["experience_band_fit"] < 0.5).astype(int)) <= 1)), "tier"] = 2
        candidates.loc[(candidates["base_fit"] >= 0.20) & (~candidates["title_chasing_flag"]) & (candidates["experience_band_fit"] >= 0.5), "tier"] = 1
        candidates.loc[candidates["base_fit"] >= 0.28, "tier"] = 1

        # Continuous Sorting Calculations using square-root availability dampening
        raw_saves = candidates["saved_by_recruiters_30d"].fillna(0).values
        raw_views = candidates["profile_views_received_30d"].fillna(0).values
        
        conversion_ratio = raw_saves / (raw_views + 1e-9)
        conversion_drag = np.where((raw_views > 45.0) & (conversion_ratio < 0.02), 0.85, 1.0)
        
        candidates["final_score"] = (candidates["base_fit"] * (candidates["availability_multiplier"] ** 0.5)) * conversion_drag

        # Priority 3: Target Location Preference Boost (Soft bias post-merit sorting)
        print("  Applying Soft Location Boost...")
        candidates["location_boost"] = compute_location_boost(candidates["location"])
        candidates["final_score"] = candidates["final_score"] + candidates["location_boost"]

        # Softened Behavioral Honeypot filter prevents false-positives
        is_behavioral_honeypot = (raw_views > 200.0) & (raw_saves == 0)
        candidates.loc[is_behavioral_honeypot, "tier"] = 4

        # Localized behavioral refinement indicators (Tie-breakers running at 1e-2 scale)
        raw_github = candidates["github_score"].fillna(0).values
        github_norm = np.maximum(0, raw_github) / 100.0
        desirability_norm = np.minimum(raw_saves, 20.0) / 20.0
        
        high_signal_industries = {'ai/ml', 'ai', 'ml', 'saas', 'fintech', 'e-commerce', 'food delivery', 'edtech'}
        raw_industries = candidates["current_industry"].fillna("generic").str.lower().str.strip().values
        industry_bonus = np.array([1.0 if ind in high_signal_industries else 0.0 for ind in raw_industries])
        startup_exposure = candidates["startup_exposure_flag"].values

        refinement_index = (0.25 * github_norm) + (0.25 * desirability_norm) + (0.25 * industry_bonus) + (0.25 * startup_exposure)

        # Lexicographical assembly
        candidates['composite_rank_score'] = ((5 - candidates['tier']) * 10.0) + candidates['final_score'] + (refinement_index * 1e-2)

        candidates = candidates.sort_values(by=["composite_rank_score", "candidate_id"], ascending=[False, True]).reset_index(drop=True)
        top100 = candidates.head(100).copy()
        top100["rank"] = range(1, 101)

        # Monotonic score generation (1.0 down to 0.0)
        c = top100["composite_rank_score"].values
        top100["score"] = (c - c.min()) / (c.max() - c.min()) if c.max() > c.min() else 1.0
        top100["score"] = top100["score"].round(6)

    # ------------------------------------------------------------------
    # STEP 7 & 8 -- DEFENSIVE REASONING AUDIT AND EXPORT
    # ------------------------------------------------------------------
    with timer("Step 7 & 8 -- Reasoning Audit & Submission Creation"):
        missing_sims = set(top100["candidate_id"]) - set(facet_sim_dict.keys())
        assert not missing_sims, f"Critical Data Error: Missing facet sims for candidates: {missing_sims}"

        # Execute text assignments over lookups verified by the asset constraint check
        top100["reasoning"] = top100.apply(lambda row: generate_reasoning(row, facet_sim_dict[row["candidate_id"]], facet_metadata), axis=1)
        
        output = top100[["candidate_id", "rank", "score", "reasoning"]].copy()
        
        assert len(output) == 100
        assert list(output["rank"]) == list(range(1, 101))
        assert all(output["score"].iloc[i] >= output["score"].iloc[i + 1] for i in range(len(output) - 1)), "Monotonicity Validation Error"
        
        output.to_csv(args.out, index=False, encoding="utf-8")
        print(f"  [SUCCESS] Submission file generated at: {args.out}")


if __name__ == "__main__":
    main()
