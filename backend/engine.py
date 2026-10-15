import os
import re
import ast
import json
import time
import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SUBMISSION_PATH = os.path.join(PROJECT_ROOT, "v2", "submission.csv")
SURVIVORS_PATH = os.path.join(PROJECT_ROOT, "v2", "survivors.csv")
FACET_METADATA_PATH = os.path.join(PROJECT_ROOT, "jd_facet_metadata.json")

class RelationalCandidateEngine:
    def __init__(self):
        # In-memory DuckDB connection for pure relational queries, joins, views, and DML
        self.con = duckdb.connect(database=":memory:")
        self.sql_transaction_logs = []
        self.current_weights = {
            "notice_sensitivity": 0.5,
            "product_bias": 0.5,
            "core_strictness": 0.5
        }
        self._init_database()

    def _log_sql(self, statement: str, operation_type: str, execution_time_ms: float, rows_affected: int = 1):
        log_entry = {
            "timestamp": time.strftime("%H:%M:%S"),
            "operation": operation_type.upper(),
            "query": statement.strip(),
            "latency_ms": round(execution_time_ms, 2),
            "rows_affected": rows_affected
        }
        self.sql_transaction_logs.insert(0, log_entry)
        if len(self.sql_transaction_logs) > 50:
            self.sql_transaction_logs.pop()

    def _init_database(self):
        print("Initializing DuckDB Relational Database Schema & Views...")
        t0 = time.perf_counter()

        # 1. Create Core Tables in 3NF
        self.con.execute("""
            CREATE TABLE Candidate (
                candidate_id VARCHAR PRIMARY KEY,
                name VARCHAR,
                headline VARCHAR,
                current_title VARCHAR,
                current_company VARCHAR,
                location VARCHAR,
                country VARCHAR DEFAULT 'India',
                total_exp_years DOUBLE,
                is_product_co BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE RedrobSignals (
                candidate_id VARCHAR PRIMARY KEY,
                notice_period_days INTEGER,
                willing_to_relocate BOOLEAN DEFAULT TRUE,
                github_activity_score DOUBLE DEFAULT 0.85,
                recruiter_response_rate DOUBLE DEFAULT 0.90,
                skill_multiplier DOUBLE DEFAULT 1.05
            );

            CREATE TABLE Skills (
                skill_id VARCHAR PRIMARY KEY,
                candidate_id VARCHAR,
                skill_name VARCHAR,
                proficiency VARCHAR,
                assessment_score DOUBLE
            );

            CREATE TABLE CareerHistory (
                history_id VARCHAR PRIMARY KEY,
                candidate_id VARCHAR,
                company VARCHAR,
                title VARCHAR,
                duration_months INTEGER,
                is_product BOOLEAN
            );

            CREATE TABLE RankingSubmission (
                candidate_id VARCHAR PRIMARY KEY,
                current_rank INTEGER,
                original_rank INTEGER,
                rank_delta INTEGER DEFAULT 0,
                score DOUBLE,
                original_score DOUBLE,
                reasoning VARCHAR
            );
        """)

        # 2. Populate tables from v2/submission.csv and v2/survivors.csv (or finalists_seed.csv)
        FINALISTS_SEED_PATH = os.path.join(PROJECT_ROOT, "backend", "finalists_seed.csv")
        if os.path.exists(SURVIVORS_PATH) and os.path.exists(SUBMISSION_PATH):
            sub_df = pd.read_csv(SUBMISSION_PATH)
            surv_df = pd.read_csv(SURVIVORS_PATH)
            merged = sub_df.merge(surv_df, on="candidate_id", how="left")
        elif os.path.exists(FINALISTS_SEED_PATH):
            merged = pd.read_csv(FINALISTS_SEED_PATH)
        elif os.path.exists(SUBMISSION_PATH):
            merged = pd.read_csv(SUBMISSION_PATH)
        else:
            raise FileNotFoundError("Could not find candidate seed data (finalists_seed.csv or submission.csv).")

        PRODUCT_COMPANIES = {
            'cred', 'swiggy', 'zomato', 'pharmeasy', 'flipkart', 'meesho', 'razorpay',
            'zepto', 'sarvam ai', 'ola', 'uber', 'amazon', 'rephrase.ai', 'nykaa',
            'upgrad', 'zoho', 'verloop.io', 'mad street den'
        }

        cand_rows = []
        sig_rows = []
        skill_rows = []
        history_rows = []
        rank_rows = []

        skill_counter = 1
        hist_counter = 1

        for _, row in merged.iterrows():
            cid = str(row["candidate_id"])
            name = str(row.get("name", "Anonymous Candidate"))
            title = str(row.get("current_title", "Search / ML Engineer"))
            comp = str(row.get("current_company", "Tech Company"))
            loc = str(row.get("location", "Noida, India"))
            yoe = float(row.get("total_exp_years", 5.0)) if pd.notna(row.get("total_exp_years")) else 5.0
            
            is_prod = any(p in comp.lower() for p in PRODUCT_COMPANIES)
            cand_rows.append((cid, name, str(row.get("headline", "")), title, comp, loc, 'India', yoe, is_prod))

            np_days = int(row.get("notice_period_days", 30)) if pd.notna(row.get("notice_period_days")) else 30
            sig_rows.append((cid, np_days, True, 0.88, 0.92, 1.15 if is_prod else 1.05))

            score = float(row.get("score", 0.8))
            rank_val = int(row.get("rank", 1))
            reason = str(row.get("reasoning", ""))
            rank_rows.append((cid, rank_val, rank_val, 0, score, score, reason))

            # Skills
            skill_rows.append((f"SK_{skill_counter}", cid, "Information Retrieval", "Advanced", min(98.0, 85.0 + score * 14)))
            skill_counter += 1
            skill_rows.append((f"SK_{skill_counter}", cid, "Vector DB & Embeddings", "Advanced", min(97.0, 82.0 + score * 15)))
            skill_counter += 1
            skill_rows.append((f"SK_{skill_counter}", cid, "PyTorch / ML Engineering", "Expert", min(95.0, 80.0 + score * 15)))
            skill_counter += 1

            # Career History
            history_rows.append((f"CH_{hist_counter}", cid, comp, title, int(yoe * 12), is_prod))
            hist_counter += 1

        self.con.executemany("INSERT INTO Candidate VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)", cand_rows)
        self.con.executemany("INSERT INTO RedrobSignals VALUES (?, ?, ?, ?, ?, ?)", sig_rows)
        self.con.executemany("INSERT INTO Skills VALUES (?, ?, ?, ?, ?)", skill_rows)
        self.con.executemany("INSERT INTO CareerHistory VALUES (?, ?, ?, ?, ?, ?)", history_rows)
        self.con.executemany("INSERT INTO RankingSubmission VALUES (?, ?, ?, ?, ?, ?, ?)", rank_rows)

        # 3. Create Pre-Compiled Relational Views (Academic Deliverable)
        self.con.execute("""
            CREATE VIEW v_immediate_product_engineers AS
            SELECT 
                c.candidate_id, 
                c.name, 
                c.current_title, 
                c.current_company, 
                c.total_exp_years, 
                s.notice_period_days,
                r.score
            FROM Candidate c
            INNER JOIN RedrobSignals s ON c.candidate_id = s.candidate_id
            INNER JOIN RankingSubmission r ON c.candidate_id = r.candidate_id
            WHERE s.notice_period_days <= 30 AND c.is_product_co = TRUE
            ORDER BY r.score DESC;

            CREATE VIEW v_verified_search_specialists AS
            SELECT 
                c.candidate_id, 
                c.name, 
                c.current_company, 
                sk.skill_name, 
                sk.assessment_score,
                r.score
            FROM Candidate c
            INNER JOIN Skills sk ON c.candidate_id = sk.candidate_id
            INNER JOIN RankingSubmission r ON c.candidate_id = r.candidate_id
            WHERE sk.assessment_score >= 92
            ORDER BY r.score DESC;

            CREATE VIEW v_candidate_dossier_joined AS
            SELECT 
                c.candidate_id,
                c.name,
                c.current_title,
                c.current_company,
                c.location,
                c.total_exp_years,
                c.is_product_co,
                s.notice_period_days,
                s.skill_multiplier,
                s.github_activity_score,
                r.current_rank,
                r.rank_delta,
                r.score,
                r.reasoning
            FROM Candidate c
            INNER JOIN RedrobSignals s ON c.candidate_id = s.candidate_id
            INNER JOIN RankingSubmission r ON c.candidate_id = r.candidate_id;
        """)

        elapsed = (time.perf_counter() - t0) * 1000
        self._log_sql(
            "CREATE TABLES Candidate, RedrobSignals, Skills, CareerHistory, RankingSubmission; CREATE VIEW v_immediate_product_engineers; CREATE VIEW v_verified_search_specialists;",
            "DDL_INIT",
            elapsed,
            len(cand_rows)
        )
        print(f"DuckDB schema & views established in {elapsed:.2f}ms")

    # -------------------------------------------------------------
    # DML: READ / SELECT
    # -------------------------------------------------------------
    def get_candidates(self, search: str = None, notice_max: int = None, product_only: bool = False, view_name: str = None):
        t0 = time.perf_counter()
        
        if view_name == "v_immediate_product_engineers":
            sql = "SELECT * FROM v_immediate_product_engineers"
            df = self.con.execute(sql).df()
            elapsed = (time.perf_counter() - t0) * 1000
            self._log_sql(sql, "SELECT_VIEW", elapsed, len(df))
            return df.to_dict(orient="records")
        elif view_name == "v_verified_search_specialists":
            sql = "SELECT * FROM v_verified_search_specialists"
            df = self.con.execute(sql).df()
            elapsed = (time.perf_counter() - t0) * 1000
            self._log_sql(sql, "SELECT_VIEW", elapsed, len(df))
            return df.to_dict(orient="records")

        # Standard Multi-Table Joined Query
        sql = """
            SELECT 
                c.candidate_id, c.name, c.headline, c.current_title, c.current_company,
                c.location, c.total_exp_years, c.is_product_co,
                s.notice_period_days, s.skill_multiplier, s.github_activity_score, s.willing_to_relocate,
                r.current_rank, r.original_rank, r.rank_delta, r.score, r.reasoning
            FROM Candidate c
            INNER JOIN RedrobSignals s ON c.candidate_id = s.candidate_id
            INNER JOIN RankingSubmission r ON c.candidate_id = r.candidate_id
            WHERE 1=1
        """
        params = []
        if search:
            sql += " AND (lower(c.name) LIKE ? OR lower(c.current_company) LIKE ? OR lower(c.current_title) LIKE ?)"
            s_param = f"%{search.lower().strip()}%"
            params.extend([s_param, s_param, s_param])
        if notice_max:
            sql += " AND s.notice_period_days <= ?"
            params.append(notice_max)
        if product_only:
            sql += " AND c.is_product_co = TRUE"

        sql += " ORDER BY r.current_rank ASC"

        df = self.con.execute(sql, params).df()
        elapsed = (time.perf_counter() - t0) * 1000
        self._log_sql(sql, "SELECT_JOIN", elapsed, len(df))

        # Attach mock facet scores for drawer rendering
        records = df.to_dict(orient="records")
        for r in records:
            r["facet_scores"] = {
                "retrieval_systems": min(99, int(85 + r["score"] * 14)),
                "vector_db_search": min(98, int(82 + r["score"] * 15)),
                "python_engineering": min(95, int(80 + r["score"] * 15)),
                "ranking_evaluation": min(96, int(84 + r["score"] * 13)),
                "learning_to_rank": min(90, int(75 + r["score"] * 15)),
                "llm_finetuning": min(85, int(70 + r["score"] * 15))
            }
        return records

    def get_candidate_detail(self, candidate_id: str):
        t0 = time.perf_counter()
        
        # 4-Table Inner and Left Join Query
        sql = """
            SELECT 
                c.candidate_id, c.name, c.headline, c.current_title, c.current_company,
                c.location, c.country, c.total_exp_years, c.is_product_co,
                s.notice_period_days, s.willing_to_relocate, s.github_activity_score, s.skill_multiplier,
                r.current_rank, r.rank_delta, r.score, r.original_score, r.reasoning
            FROM Candidate c
            INNER JOIN RedrobSignals s ON c.candidate_id = s.candidate_id
            INNER JOIN RankingSubmission r ON c.candidate_id = r.candidate_id
            WHERE c.candidate_id = ?
        """
        cand_df = self.con.execute(sql, [candidate_id]).df()
        if cand_df.empty:
            return None

        # Fetch skills
        skills_sql = "SELECT skill_name, proficiency, assessment_score FROM Skills WHERE candidate_id = ?"
        skills_df = self.con.execute(skills_sql, [candidate_id]).df()

        # Fetch career history
        hist_sql = "SELECT company, title, duration_months, is_product FROM CareerHistory WHERE candidate_id = ?"
        hist_df = self.con.execute(hist_sql, [candidate_id]).df()

        elapsed = (time.perf_counter() - t0) * 1000
        self._log_sql(f"{sql}; {skills_sql}; {hist_sql}", "MULTI_TABLE_JOIN", elapsed, 1)

        record = cand_df.iloc[0].to_dict()
        record["skills"] = skills_df.to_dict(orient="records")
        record["career_history"] = hist_df.to_dict(orient="records")
        record["facet_scores"] = {
            "retrieval_systems": min(99, int(85 + record["score"] * 14)),
            "vector_db_search": min(98, int(82 + record["score"] * 15)),
            "python_engineering": min(95, int(80 + record["score"] * 15)),
            "ranking_evaluation": min(96, int(84 + record["score"] * 13)),
            "learning_to_rank": min(90, int(75 + record["score"] * 15)),
            "llm_finetuning": min(85, int(70 + record["score"] * 15))
        }
        return record

    # -------------------------------------------------------------
    # DML: INSERT (Candidate Registration)
    # -------------------------------------------------------------
    def insert_candidate(self, data: dict):
        t0 = time.perf_counter()
        cid = data.get("candidate_id") or f"CAND_{int(time.time()) % 1000000:07d}"
        name = data.get("name", "New Candidate")
        headline = data.get("headline", "AI & Machine Learning Engineer")
        title = data.get("current_title", "ML Engineer")
        company = data.get("current_company", "Independent")
        location = data.get("location", "Bengaluru, India")
        yoe = float(data.get("total_exp_years", 4.0))
        is_product = bool(data.get("is_product_co", True))
        notice_days = int(data.get("notice_period_days", 15))

        insert_cand_sql = """
            INSERT INTO Candidate (candidate_id, name, headline, current_title, current_company, location, total_exp_years, is_product_co)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        self.con.execute(insert_cand_sql, [cid, name, headline, title, company, location, yoe, is_product])

        insert_sig_sql = """
            INSERT INTO RedrobSignals (candidate_id, notice_period_days, willing_to_relocate, github_activity_score, skill_multiplier)
            VALUES (?, ?, TRUE, 0.90, ?)
        """
        skill_mult = 1.15 if is_product else 1.05
        self.con.execute(insert_sig_sql, [cid, notice_days, skill_mult])

        # Add initial rank entry
        max_rank_row = self.con.execute("SELECT MAX(current_rank) AS max_r FROM RankingSubmission").df()
        next_rank = int(max_rank_row["max_r"].iloc[0] or 100) + 1
        initial_score = round(min(0.999, 0.70 + (yoe / 20.0) * 0.2), 4)
        reasoning = f"New candidate profile registered: {yoe}y YoE in ML engineering at {company}, {notice_days}d notice."

        insert_rank_sql = """
            INSERT INTO RankingSubmission (candidate_id, current_rank, original_rank, rank_delta, score, original_score, reasoning)
            VALUES (?, ?, ?, 0, ?, ?, ?)
        """
        self.con.execute(insert_rank_sql, [cid, next_rank, next_rank, initial_score, initial_score, reasoning])

        # Skills & Career History
        skills_list = data.get("skills") or ["Vector Indexing", "PyTorch", "Information Retrieval"]
        for idx, sk in enumerate(skills_list):
            sk_id = f"SK_{cid}_{idx}"
            self.con.execute(
                "INSERT INTO Skills (skill_id, candidate_id, skill_name, proficiency, assessment_score) VALUES (?, ?, ?, 'Advanced', 92.0)",
                [sk_id, cid, sk]
            )

        hist_id = f"HIST_{cid}_1"
        self.con.execute(
            "INSERT INTO CareerHistory (history_id, candidate_id, company, title, duration_months, is_product) VALUES (?, ?, ?, ?, 36, ?)",
            [hist_id, cid, company, title, is_product]
        )

        elapsed = (time.perf_counter() - t0) * 1000
        full_sql = f"INSERT INTO Candidate VALUES ('{cid}', '{name}', ...); INSERT INTO RedrobSignals VALUES ('{cid}', {notice_days}, ...); INSERT INTO RankingSubmission VALUES ('{cid}', {next_rank}, ...); INSERT INTO Skills VALUES (...);"
        self._log_sql(full_sql, "INSERT_DML", elapsed, 5)

        return self.get_candidate_detail(cid)

    # -------------------------------------------------------------
    # DML: UPDATE (Candidate Profile Modification)
    # -------------------------------------------------------------
    def update_candidate(self, candidate_id: str, data: dict):
        t0 = time.perf_counter()
        
        # 1. Update Candidate table
        update_cand_parts = []
        cand_params = []
        if "name" in data:
            update_cand_parts.append("name = ?")
            cand_params.append(data["name"])
        if "current_title" in data:
            update_cand_parts.append("current_title = ?")
            cand_params.append(data["current_title"])
        if "current_company" in data:
            update_cand_parts.append("current_company = ?")
            cand_params.append(data["current_company"])
        if "location" in data:
            update_cand_parts.append("location = ?")
            cand_params.append(data["location"])
        if "total_exp_years" in data:
            update_cand_parts.append("total_exp_years = ?")
            cand_params.append(float(data["total_exp_years"]))
        if "is_product_co" in data:
            update_cand_parts.append("is_product_co = ?")
            cand_params.append(bool(data["is_product_co"]))

        if update_cand_parts:
            cand_params.append(candidate_id)
            sql_cand = f"UPDATE Candidate SET {', '.join(update_cand_parts)} WHERE candidate_id = ?"
            self.con.execute(sql_cand, cand_params)

        # 2. Update RedrobSignals table
        update_sig_parts = []
        sig_params = []
        if "notice_period_days" in data:
            update_sig_parts.append("notice_period_days = ?")
            sig_params.append(int(data["notice_period_days"]))
        if "willing_to_relocate" in data:
            update_sig_parts.append("willing_to_relocate = ?")
            sig_params.append(bool(data["willing_to_relocate"]))

        if update_sig_parts:
            sig_params.append(candidate_id)
            sql_sig = f"UPDATE RedrobSignals SET {', '.join(update_sig_parts)} WHERE candidate_id = ?"
            self.con.execute(sql_sig, sig_params)

        elapsed = (time.perf_counter() - t0) * 1000
        sql_log = f"UPDATE Candidate SET ... WHERE candidate_id = '{candidate_id}'; UPDATE RedrobSignals SET ... WHERE candidate_id = '{candidate_id}';"
        self._log_sql(sql_log, "UPDATE_DML", elapsed, 1)

        # Re-rank in-memory so leaderboard updates live!
        self.rerank(
            notice_sensitivity=self.current_weights["notice_sensitivity"],
            product_bias=self.current_weights["product_bias"],
            core_strictness=self.current_weights["core_strictness"]
        )

        return self.get_candidate_detail(candidate_id)

    # -------------------------------------------------------------
    # DML: DELETE (Withdraw Candidacy)
    # -------------------------------------------------------------
    def delete_candidate(self, candidate_id: str):
        t0 = time.perf_counter()
        
        del_rank = "DELETE FROM RankingSubmission WHERE candidate_id = ?"
        del_sig = "DELETE FROM RedrobSignals WHERE candidate_id = ?"
        del_skills = "DELETE FROM Skills WHERE candidate_id = ?"
        del_hist = "DELETE FROM CareerHistory WHERE candidate_id = ?"
        del_cand = "DELETE FROM Candidate WHERE candidate_id = ?"

        self.con.execute(del_rank, [candidate_id])
        self.con.execute(del_sig, [candidate_id])
        self.con.execute(del_skills, [candidate_id])
        self.con.execute(del_hist, [candidate_id])
        self.con.execute(del_cand, [candidate_id])

        elapsed = (time.perf_counter() - t0) * 1000
        full_sql = f"DELETE FROM RankingSubmission WHERE candidate_id = '{candidate_id}'; DELETE FROM Candidate WHERE candidate_id = '{candidate_id}';"
        self._log_sql(full_sql, "DELETE_DML", elapsed, 5)

        # Recompute ranks
        self.rerank(
            notice_sensitivity=self.current_weights["notice_sensitivity"],
            product_bias=self.current_weights["product_bias"],
            core_strictness=self.current_weights["core_strictness"]
        )
        return {"status": "deleted", "candidate_id": candidate_id}

    # -------------------------------------------------------------
    # RE-RANKING & CALCULATION
    # -------------------------------------------------------------
    def rerank(self, notice_sensitivity: float, product_bias: float, core_strictness: float):
        t0 = time.perf_counter()
        self.current_weights = {
            "notice_sensitivity": notice_sensitivity,
            "product_bias": product_bias,
            "core_strictness": core_strictness
        }

        # Pull all candidate ranking inputs
        df = self.con.execute("""
            SELECT 
                c.candidate_id,
                r.original_score,
                r.original_rank,
                s.notice_period_days,
                c.is_product_co
            FROM Candidate c
            INNER JOIN RedrobSignals s ON c.candidate_id = s.candidate_id
            INNER JOIN RankingSubmission r ON c.candidate_id = r.candidate_id
        """).df()

        scores = []
        for _, row in df.iterrows():
            base = float(row["original_score"])
            np_days = int(row["notice_period_days"])

            # Notice factor
            if np_days <= 30:
                notice_factor = 1.0 + (0.15 * notice_sensitivity)
            elif np_days <= 60:
                notice_factor = 1.0 - (0.05 * notice_sensitivity)
            elif np_days <= 90:
                notice_factor = 1.0 - (0.15 * notice_sensitivity)
            else:
                notice_factor = 1.0 - (0.30 * notice_sensitivity)

            # Product co factor
            prod_factor = 1.0 + (0.20 * product_bias) if row["is_product_co"] else 1.0 - (0.10 * product_bias)

            scores.append(base * notice_factor * prod_factor)

        df["new_score"] = scores
        df = df.sort_values(by="new_score", ascending=False).reset_index(drop=True)
        df["current_rank"] = np.arange(1, len(df) + 1)
        max_s = df["new_score"].max()
        df["score"] = (df["new_score"] / max_s).round(4) if max_s > 0 else df["new_score"].round(4)
        df["rank_delta"] = df["original_rank"] - df["current_rank"]

        # Batch update back into DuckDB RankingSubmission table
        updates = [(int(r["current_rank"]), int(r["rank_delta"]), float(r["score"]), str(r["candidate_id"])) for _, r in df.iterrows()]
        self.con.executemany("""
            UPDATE RankingSubmission 
            SET current_rank = ?, rank_delta = ?, score = ?
            WHERE candidate_id = ?
        """, updates)

        elapsed = (time.perf_counter() - t0) * 1000
        self._log_sql(
            f"UPDATE RankingSubmission SET current_rank, rank_delta, score [Batch {len(updates)} rows];",
            "RE_RANK_DML",
            elapsed,
            len(updates)
        )

        return {
            "status": "success",
            "latency_ms": round(elapsed, 1),
            "weights": self.current_weights,
            "candidates": self.get_candidates()
        }

    # -------------------------------------------------------------
    # CUSTOM SQL QUERY EXECUTION (For Professor Sandbox Terminal)
    # -------------------------------------------------------------
    def execute_custom_sql(self, query: str):
        t0 = time.perf_counter()
        q = query.strip()
        try:
            res_df = self.con.execute(q).df()
            elapsed = (time.perf_counter() - t0) * 1000
            
            # Detect statement type
            op_type = "CUSTOM_SELECT"
            if q.upper().startswith("INSERT"): op_type = "CUSTOM_INSERT"
            elif q.upper().startswith("UPDATE"): op_type = "CUSTOM_UPDATE"
            elif q.upper().startswith("DELETE"): op_type = "CUSTOM_DELETE"
            elif q.upper().startswith("CREATE"): op_type = "CUSTOM_DDL"

            self._log_sql(q, op_type, elapsed, len(res_df))

            # Limit output to 100 rows for display safety
            columns = list(res_df.columns)
            rows = res_df.head(100).to_dict(orient="records")

            return {
                "success": True,
                "columns": columns,
                "rows": rows,
                "total_rows": len(res_df),
                "latency_ms": round(elapsed, 2)
            }
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            self._log_sql(q, "ERROR", elapsed, 0)
            return {
                "success": False,
                "error": str(e),
                "latency_ms": round(elapsed, 2)
            }

    def get_sql_logs(self):
        return self.sql_transaction_logs

relational_engine = RelationalCandidateEngine()
