import os
import io
import pandas as pd
from typing import List, Optional
from fastapi import FastAPI, Query, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from backend.engine import engine

app = FastAPI(title="Assay Talent Intelligence API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ReRankRequest(BaseModel):
    notice_sensitivity: float = 0.5
    product_bias: float = 0.5
    core_strictness: float = 0.5

class CompareRequest(BaseModel):
    candidate_ids: List[str]

@app.get("/api/health")
def health():
    return {"status": "ok", "engine": "Assay Hybrid SQL & Vector Engine"}

@app.get("/api/telemetry")
def get_telemetry():
    return engine.get_telemetry()

@app.get("/api/candidates")
def list_candidates(
    search: Optional[str] = None,
    notice_max: Optional[int] = None,
    product_only: Optional[bool] = False
):
    return engine.get_candidates(search=search, notice_max=notice_max, product_only=product_only)

@app.get("/api/candidates/{candidate_id}")
def get_candidate(candidate_id: str):
    cand = engine.get_candidate_detail(candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return cand

@app.post("/api/rerank")
def rerank(req: ReRankRequest):
    return engine.rerank(
        notice_sensitivity=req.notice_sensitivity,
        product_bias=req.product_bias,
        core_strictness=req.core_strictness
    )

@app.post("/api/compare")
def compare_candidates(req: CompareRequest):
    return engine.compare(req.candidate_ids)

@app.get("/api/export")
def export_csv():
    cands = engine.get_candidates()
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

# Mount frontend web static files
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
