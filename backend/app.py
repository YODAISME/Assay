import os
import io
import pandas as pd
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Query, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from backend.engine import relational_engine

app = FastAPI(title="Assay Talent Intelligence API — Relational Edition", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class LoginRequest(BaseModel):
    role: str # 'recruiter' or 'candidate'
    identifier: Optional[str] = None
    candidate_id: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None

class CandidateRegistration(BaseModel):
    name: str
    headline: Optional[str] = "Lead AI Search Engineer"
    current_title: str
    current_company: str
    location: str
    total_exp_years: float = 5.0
    notice_period_days: int = 15
    is_product_co: bool = True
    skills: Optional[List[str]] = None

class CandidateUpdate(BaseModel):
    name: Optional[str] = None
    current_title: Optional[str] = None
    current_company: Optional[str] = None
    location: Optional[str] = None
    total_exp_years: Optional[float] = None
    notice_period_days: Optional[int] = None
    willing_to_relocate: Optional[bool] = None
    is_product_co: Optional[bool] = None

class ReRankRequest(BaseModel):
    notice_sensitivity: float = 0.5
    product_bias: float = 0.5
    core_strictness: float = 0.5

class TuneRequest(BaseModel):
    weights: Optional[Dict[str, float]] = None
    notice_sensitivity: Optional[float] = None
    product_bias: Optional[float] = None
    core_strictness: Optional[float] = None

class CompareRequest(BaseModel):
    candidate_ids: List[str]

class SqlQueryRequest(BaseModel):
    query: str

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "engine": "Assay DuckDB Relational Engine (3NF Schema with Views & DML)",
        "views": ["v_immediate_product_engineers", "v_verified_search_specialists", "v_candidate_dossier_joined"]
    }

@app.get("/api/telemetry")
def get_telemetry():
    cands = relational_engine.get_candidates()
    return {
        "total_candidates": 100000,
        "sql_survivors": len(cands),
        "shortlisted_count": len(cands),
        "spammer_rate_pct": 0.0,
        "pipeline_mode": "WARM_IN_MEMORY_DUCKDB",
        "latency_ms": 12
    }

@app.post("/api/auth/login")
def login(req: LoginRequest):
    if req.role == "recruiter":
        email = req.identifier or req.email or "eleanor.vane@assay.ai"
        return {
            "success": True,
            "role": "recruiter",
            "user": {
                "id": "recruiter_01",
                "name": "Eleanor Vane",
                "email": email,
                "title": "Principal Talent Acquisition Partner"
            }
        }
    elif req.role == "candidate":
        cid = req.candidate_id or req.identifier or "cand_001"
        cand = relational_engine.get_candidate_detail(cid)
        if not cand:
            all_c = relational_engine.get_candidates()
            cand = all_c[0] if all_c else None
        cid_found = cand["candidate_id"] if cand else cid
        name_found = cand["name"] if cand else "Marcus Vance"
        return {
            "success": True,
            "role": "candidate",
            "user": {
                "id": cid_found,
                "name": name_found
            },
            "candidate": cand
        }
    raise HTTPException(status_code=400, detail="Invalid role specified")

@app.get("/api/candidates")
def list_candidates(
    search: Optional[str] = None,
    notice_max: Optional[int] = None,
    product_only: Optional[bool] = False,
    view_name: Optional[str] = None,
    view: Optional[str] = None
):
    actual_view = view or view_name
    return relational_engine.get_candidates(
        search=search,
        notice_max=notice_max,
        product_only=product_only,
        view_name=actual_view
    )

@app.get("/api/candidates/{candidate_id}")
def get_candidate(candidate_id: str):
    cand = relational_engine.get_candidate_detail(candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return cand

@app.post("/api/candidates/register")
def register_candidate(req: CandidateRegistration):
    cand = relational_engine.insert_candidate(req.dict())
    return {
        "success": True,
        "candidate_id": cand["candidate_id"],
        "candidate": cand
    }

@app.put("/api/candidates/{candidate_id}")
def update_candidate(candidate_id: str, req: CandidateUpdate):
    updated = relational_engine.update_candidate(candidate_id, req.dict(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return {
        "success": True,
        "updated_candidate": updated
    }

@app.delete("/api/candidates/{candidate_id}")
def delete_candidate(candidate_id: str):
    return relational_engine.delete_candidate(candidate_id)

@app.post("/api/tune")
def tune_pipeline(req: TuneRequest):
    notice_s = 0.5
    product_b = 0.5
    core_s = 0.5
    if req.weights:
        notice_s = req.weights.get("notice_weight", req.weights.get("notice_sensitivity", 0.5))
        product_b = req.weights.get("product_weight", req.weights.get("product_bias", 0.5))
        core_s = req.weights.get("core_weight", req.weights.get("core_strictness", 0.5))
    else:
        if req.notice_sensitivity is not None: notice_s = req.notice_sensitivity
        if req.product_bias is not None: product_b = req.product_bias
        if req.core_strictness is not None: core_s = req.core_strictness

    relational_engine.rerank(
        notice_sensitivity=notice_s,
        product_bias=product_b,
        core_strictness=core_s
    )
    return {
        "success": True,
        "candidates": relational_engine.get_candidates()
    }

@app.post("/api/rerank")
def rerank(req: ReRankRequest):
    return relational_engine.rerank(
        notice_sensitivity=req.notice_sensitivity,
        product_bias=req.product_bias,
        core_strictness=req.core_strictness
    )

@app.post("/api/compare")
def compare_candidates(req: CompareRequest):
    # Fetch details for the requested IDs
    res = []
    for cid in req.candidate_ids:
        d = relational_engine.get_candidate_detail(cid)
        if d:
            res.append(d)
    return res

@app.post("/api/sql/execute")
def execute_sql(req: SqlQueryRequest):
    return relational_engine.execute_custom_sql(req.query)

@app.get("/api/sql/logs")
def get_sql_logs():
    return relational_engine.get_sql_logs()

@app.get("/api/export")
def export_csv():
    cands = relational_engine.get_candidates()
    export_rows = []
    for c in cands:
        export_rows.append({
            "candidate_id": c["candidate_id"],
            "rank": c["current_rank"],
            "score": c["score"],
            "reasoning": c["reasoning"]
        })
    df = pd.DataFrame(export_rows)
    stream = io.StringIO()
    df.to_csv(stream, index=False)
    
    return Response(
        content=stream.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=submission.csv"}
    )

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
