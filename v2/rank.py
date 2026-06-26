import argparse
import duckdb
import pandas as pd

def run_pipeline(candidates_path, output_path):
    # Connect to local in-memory database instance
    con = duckdb.connect(database=':memory:')

    print(f"Streaming and analyzing candidates from: {candidates_path}...\n")

    # Precise column schema mapping candidate_schema.json properties
    SCHEMA_COLUMNS = {
        'candidate_id': 'VARCHAR',
        'profile': 'STRUCT(anonymized_name VARCHAR, headline VARCHAR, summary VARCHAR, location VARCHAR, country VARCHAR, years_of_experience DOUBLE, current_title VARCHAR, current_company VARCHAR, current_company_size VARCHAR, current_industry VARCHAR)',
        'skills': 'STRUCT(name VARCHAR, proficiency VARCHAR, endorsements INT, duration_months INT)[]',
        'career_history': 'STRUCT(company VARCHAR, title VARCHAR, start_date VARCHAR, end_date VARCHAR, duration_months INT, is_current BOOLEAN, industry VARCHAR, company_size VARCHAR, description VARCHAR)[]',
        'redrob_signals': 'STRUCT(profile_completeness_score DOUBLE, signup_date VARCHAR, last_active_date VARCHAR, open_to_work_flag BOOLEAN, profile_views_received_30d INT, applications_submitted_30d INT, recruiter_response_rate DOUBLE, avg_response_time_hours DOUBLE, connection_count INT, endorsements_received INT, notice_period_days INT, preferred_work_mode VARCHAR, willing_to_relocate BOOLEAN, github_activity_score DOUBLE, search_appearance_30d INT, saved_by_recruiters_30d INT, interview_completion_rate DOUBLE, offer_acceptance_rate DOUBLE, verified_email BOOLEAN, verified_phone BOOLEAN, linkedin_connected BOOLEAN)'
    }

    # Consulting firms — candidates whose ENTIRE career history consists only
    # of these are excluded. Any prior product-company experience clears them.
    CONSULTING_FIRMS = "'tcs', 'infosys', 'wipro', 'accenture', 'cognizant', 'capgemini', 'tech mahindra', 'mindtree', 'hcl'"

    # 1. RUN METRICS SCAN (Evaluates why candidates fail)
    metrics_query = f"""
    WITH evaluated_candidates AS (
        SELECT
            candidate_id,

            -- Prong 1 Flag: location/relocation eligibility
            (
                profile.location LIKE 'Pune%'
                OR profile.location LIKE 'Noida%'
                OR profile.location LIKE 'Hyderabad%'
                OR profile.location LIKE 'Mumbai%'
                OR profile.location LIKE 'Delhi%'
                OR profile.location LIKE 'Gurgaon%'
                OR (redrob_signals.willing_to_relocate = true AND profile.country = 'India')
            ) AS pass_location,

            -- Prong 2 Flag: role/track exclusions + consulting-only exclusion
            -- Relaxed version: research and sales engineers are allowed through.
            (
                lower(profile.current_title) NOT LIKE '%marketing manager%'
                AND lower(profile.current_title) NOT LIKE '%accountant%'
                AND lower(profile.current_title) NOT LIKE '%recruiter%'
                AND lower(profile.current_title) NOT LIKE '%human resources%'
                AND lower(profile.current_title) NOT LIKE '%hr manager%'
                AND lower(profile.current_title) NOT LIKE '%hr executive%'
                
                -- Exclude sales unless they are an engineer/architect/developer/specialist
                AND NOT (
                    lower(profile.current_title) LIKE '%sales%'
                    AND lower(profile.current_title) NOT LIKE '%engineer%'
                    AND lower(profile.current_title) NOT LIKE '%developer%'
                    AND lower(profile.current_title) NOT LIKE '%specialist%'
                    AND lower(profile.current_title) NOT LIKE '%architect%'
                )

                -- Consulting-only exclusion
                AND NOT (
                    len(career_history) > 0
                    AND len(list_filter(career_history, h ->
                        lower(h.company) NOT IN ({CONSULTING_FIRMS})
                    )) = 0
                )
            ) AS pass_role
        FROM read_json_auto('{candidates_path}', columns={SCHEMA_COLUMNS}, format='newline_delimited')
    )
    SELECT
        COUNT(*) AS total_pool,
        COUNT(*) - SUM(CASE WHEN pass_location THEN 1 ELSE 0 END) AS failed_location,
        COUNT(*) - SUM(CASE WHEN pass_role THEN 1 ELSE 0 END) AS failed_role,
        SUM(CASE WHEN pass_location AND pass_role THEN 1 ELSE 0 END) AS total_survived
    FROM evaluated_candidates;
    """

    metrics_df = con.execute(metrics_query).df()

    # Display statistics breakdown
    print("=" * 60)
    print("             FILTER REJECTION BREAKDOWN               ")
    print("=" * 60)
    print(f"Total Candidates Evaluated : {metrics_df['total_pool'][0]:,}")
    print("-" * 60)
    print(f"Removed by Location Check   : {metrics_df['failed_location'][0]:,}")
    print(f"Removed by Role/Track Check : {metrics_df['failed_role'][0]:,}")
    print("-" * 60)
    print(f"Final Surviving Candidates  : {metrics_df['total_survived'][0]:,}")
    print("=" * 60 + "\n")

    # 2. EXTRACTION AND COMPILATION RUN
    extraction_query = f"""
    SELECT
        candidate_id,
        profile.anonymized_name AS name,
        profile.headline AS headline,
        profile.summary AS summary,
        profile.current_title AS current_title,
        profile.current_company AS current_company,
        profile.location AS location,
        profile.country AS country,
        profile.years_of_experience AS total_exp_years,
        skills,
        career_history,
        redrob_signals.recruiter_response_rate AS response_rate,
        redrob_signals.last_active_date AS last_active,
        redrob_signals.open_to_work_flag AS open_to_work,
        redrob_signals.preferred_work_mode AS work_mode,
        redrob_signals.willing_to_relocate AS willing_to_relocate,
        redrob_signals.notice_period_days AS notice_period_days,
        redrob_signals.github_activity_score AS github_activity_score,
        redrob_signals.interview_completion_rate AS interview_completion_rate,
        redrob_signals.offer_acceptance_rate AS offer_acceptance_rate,
        redrob_signals.profile_completeness_score AS profile_completeness_score
    FROM read_json_auto('{candidates_path}', columns={SCHEMA_COLUMNS}, format='newline_delimited')
    WHERE
        -- Prong 1: Location / relocation funnel
        (
            profile.location LIKE 'Pune%'
            OR profile.location LIKE 'Noida%'
            OR profile.location LIKE 'Hyderabad%'
            OR profile.location LIKE 'Mumbai%'
            OR profile.location LIKE 'Delhi%'
            OR profile.location LIKE 'Gurgaon%'
            OR (redrob_signals.willing_to_relocate = true AND profile.country = 'India')
        )

        -- Prong 2: Role & track exclusions + consulting-only exclusion
        AND lower(profile.current_title) NOT LIKE '%marketing manager%'
        AND lower(profile.current_title) NOT LIKE '%accountant%'
        AND lower(profile.current_title) NOT LIKE '%recruiter%'
        AND lower(profile.current_title) NOT LIKE '%human resources%'
        AND lower(profile.current_title) NOT LIKE '%hr manager%'
        AND lower(profile.current_title) NOT LIKE '%hr executive%'
        
        -- Exclude sales unless they are an engineer/architect/developer/specialist
        AND NOT (
            lower(profile.current_title) LIKE '%sales%'
            AND lower(profile.current_title) NOT LIKE '%engineer%'
            AND lower(profile.current_title) NOT LIKE '%developer%'
            AND lower(profile.current_title) NOT LIKE '%specialist%'
            AND lower(profile.current_title) NOT LIKE '%architect%'
        )

        AND NOT (
            len(career_history) > 0
            AND len(list_filter(career_history, h ->
                lower(h.company) NOT IN ({CONSULTING_FIRMS})
            )) = 0
        );
    """

    result_df = con.execute(extraction_query).df()
    result_df.to_csv(output_path, index=False)
    print(f"[SUCCESS] Saved complete filtered subset ({len(result_df):,} candidates) to: {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pre-Filtering Pipeline — location + role/track soft filter")
    parser.add_argument("--candidates", required=True, help="Input path targeting candidates.jsonl")
    parser.add_argument("--out", required=True, help="Output path for the filtered dataset CSV")
    args = parser.parse_args()

    run_pipeline(args.candidates, args.out)
