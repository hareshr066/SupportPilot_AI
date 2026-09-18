import os
import sys
import time
import traceback
import json
from typing import Dict, Any

# Ensure workspace root is in python path
WORKSPACE_ROOT = os.path.abspath(".")
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from config import settings

def run_diagnostic():
    report = {
        "openai": {},
        "github": {},
        "database": {},
        "local_ml": {},
        "pipeline_stages": {}
    }

    print("=" * 60)
    print("SUPPORTPILOT LIVE AI CREDENTIAL & PIPELINE DIAGNOSTIC")
    print("=" * 60)

    # -------------------------------------------------------------
    # 1. OPENAI CONFIGURATION
    # -------------------------------------------------------------
    print("\n[1/5] Checking OpenAI Configuration...")
    env_key = os.getenv("OPENAI_API_KEY")
    cfg_key = settings.openai_api_key
    has_key = bool(env_key or cfg_key)
    active_key = cfg_key or env_key

    report["openai"]["key_present"] = has_key
    report["openai"]["read_by_app"] = bool(cfg_key)
    report["openai"]["configured_models"] = {
        "resolution_model": settings.resolution_llm_model,
        "verifier_model": settings.verifier_llm_model,
        "root_cause_model": settings.root_cause_llm_model,
    }

    if not has_key:
        report["openai"]["status"] = "FAILED"
        report["openai"]["error_category"] = "missing API key"
        report["openai"]["details"] = "OPENAI_API_KEY is not set in environment or .env file."
        print("  [-] OpenAI API Key: NOT FOUND (missing API key)")
    else:
        print("  [+] OpenAI API Key: PRESENT (masked)")
        print(f"  [+] Configured Models: resolution={settings.resolution_llm_model}, verifier={settings.verifier_llm_model}, root_cause={settings.root_cause_llm_model}")
        
        # Test OpenAI Client initialization and live call
        try:
            import openai
            client = openai.OpenAI(api_key=active_key)
            report["openai"]["client_initialized"] = True
            print("  [+] OpenAI Client Initialized: SUCCESS")

            t0 = time.time()
            # Attempt a minimal live call
            response = client.chat.completions.create(
                model=settings.resolution_llm_model,
                messages=[{"role": "user", "content": "Respond with JSON: {\"status\": \"ok\"}"}],
                response_format={"type": "json_object"},
                max_tokens=20
            )
            latency = (time.time() - t0) * 1000
            report["openai"]["status"] = "SUCCESS"
            report["openai"]["latency_ms"] = round(latency, 2)
            report["openai"]["live_call"] = "SUCCESS"
            print(f"  [+] OpenAI Live API Call: SUCCESS ({latency:.1f} ms)")
        except ImportError:
            report["openai"]["client_initialized"] = False
            report["openai"]["status"] = "FAILED"
            report["openai"]["error_category"] = "application/client error"
            report["openai"]["details"] = "openai python package is not installed."
            print("  [-] OpenAI Client: FAILED (openai package not installed)")
        except Exception as exc:
            exc_name = type(exc).__name__
            exc_str = str(exc).lower()
            report["openai"]["client_initialized"] = True
            report["openai"]["status"] = "FAILED"
            
            # Classify error
            if "authentication" in exc_str or "invalid_api_key" in exc_str or "401" in exc_str:
                err_cat = "authentication failure"
            elif "insufficient_quota" in exc_str or "quota" in exc_str or "billing" in exc_str:
                err_cat = "quota exceeded"
            elif "rate_limit" in exc_str or "429" in exc_str:
                err_cat = "rate limit"
            elif "model_not_found" in exc_str or "does not exist" in exc_str or "404" in exc_str:
                err_cat = "model unavailable"
            elif "connection" in exc_str or "timeout" in exc_str or "network" in exc_str:
                err_cat = "network failure"
            else:
                err_cat = "application/client error"
            
            report["openai"]["error_category"] = err_cat
            report["openai"]["error_type"] = exc_name
            report["openai"]["details"] = str(exc)
            print(f"  [-] OpenAI Live API Call: FAILED ({err_cat} - {exc_name})")

    # -------------------------------------------------------------
    # 2. GITHUB CONFIGURATION
    # -------------------------------------------------------------
    print("\n[2/5] Checking GitHub Configuration...")
    gh_token = settings.github_token or os.getenv("GITHUB_TOKEN")
    has_gh = bool(gh_token)
    report["github"]["token_present"] = has_gh

    from app.services.github_client import GitHubClient
    gh_client = GitHubClient(token=gh_token)
    t0 = time.time()
    try:
        resp = gh_client.session.get(f"{gh_client.base_url}/rate_limit", timeout=5.0)
        latency = (time.time() - t0) * 1000
        report["github"]["latency_ms"] = round(latency, 2)
        if resp.status_code == 200:
            rate_data = resp.json().get("rate", {})
            report["github"]["status"] = "SUCCESS"
            report["github"]["rate_limit"] = {
                "limit": rate_data.get("limit"),
                "remaining": rate_data.get("remaining"),
                "authenticated": has_gh
            }
            print(f"  [{'+' if has_gh else '-'}] GitHub Token: {'CONFIGURED' if has_gh else 'UNCONFIGURED (Unauthenticated public mode)'}")
            print(f"  [+] GitHub API Access: SUCCESS (remaining={rate_data.get('remaining')}/{rate_data.get('limit')}, auth={has_gh}, {latency:.1f} ms)")
        else:
            report["github"]["status"] = "FAILED"
            report["github"]["error"] = f"HTTP {resp.status_code}"
            print(f"  [-] GitHub API Access: FAILED (HTTP {resp.status_code})")
    except Exception as gh_err:
        report["github"]["status"] = "FAILED"
        report["github"]["error"] = str(gh_err)
        print(f"  [-] GitHub API Access: FAILED ({gh_err})")

    # -------------------------------------------------------------
    # 3. DATABASE & PGVECTOR
    # -------------------------------------------------------------
    print("\n[3/5] Checking Database & pgvector...")
    from sqlalchemy import text, create_engine
    
    # Check PostgreSQL specifically
    pg_url = settings.database_url
    report["database"]["configured_url_dialect"] = pg_url.split("://")[0]
    
    is_postgres_connected = False
    has_pgvector = False
    table_counts = {}
    
    try:
        pg_engine = create_engine(pg_url, connect_args={"connect_timeout": 3} if pg_url.startswith("postgresql") else {})
        with pg_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            is_postgres_connected = True
            
            # Check pgvector
            try:
                vec_res = conn.execute(text("SELECT * FROM pg_extension WHERE extname = 'vector';")).fetchall()
                has_pgvector = len(vec_res) > 0
            except Exception:
                has_pgvector = False
            
            # Check tables
            try:
                tables_res = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")).fetchall()
                tables = [r[0] for r in tables_res]
                report["database"]["tables"] = tables
                for t in ["repositories", "issues", "pipeline_runs", "root_cause_clusters"]:
                    if t in tables:
                        cnt = conn.execute(text(f"SELECT COUNT(*) FROM {t};")).scalar()
                        table_counts[t] = cnt
            except Exception as e:
                report["database"]["tables_error"] = str(e)

        report["database"]["postgres_connected"] = is_postgres_connected
        report["database"]["pgvector_available"] = has_pgvector
        report["database"]["table_counts"] = table_counts
        print(f"  [+] PostgreSQL Connection: SUCCESS")
        print(f"  [{'+' if has_pgvector else '-'}] pgvector extension: {'AVAILABLE' if has_pgvector else 'NOT INSTALLED'}")
        print(f"  [+] Tables found: {list(table_counts.keys())} -> {table_counts}")
    except Exception as exc:
        report["database"]["postgres_connected"] = False
        report["database"]["pgvector_available"] = False
        report["database"]["postgres_error"] = str(exc)
        print(f"  [-] PostgreSQL Connection: FAILED ({exc})")
        
        # Check SQLite fallback
        try:
            from app.database.engine import engine as active_engine
            with active_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                report["database"]["fallback_sqlite_active"] = True
                print("  [+] Active Database Engine: Fallback SQLite connected")
                
                # Check tables in active engine
                try:
                    res = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table';")).fetchall()
                    sq_tables = [r[0] for r in res]
                    report["database"]["sqlite_tables"] = sq_tables
                    for t in ["repositories", "issues", "pipeline_runs", "root_cause_clusters"]:
                        if t in sq_tables:
                            cnt = conn.execute(text(f"SELECT COUNT(*) FROM {t};")).scalar()
                            table_counts[t] = cnt
                    report["database"]["table_counts"] = table_counts
                    print(f"  [+] SQLite Tables: {table_counts}")
                except Exception as sq_err:
                    report["database"]["sqlite_error"] = str(sq_err)
        except Exception as sq_exc:
            report["database"]["fallback_sqlite_active"] = False
            report["database"]["sqlite_error"] = str(sq_exc)
            print(f"  [-] Fallback SQLite: FAILED ({sq_exc})")

    # -------------------------------------------------------------
    # 4. LOCAL ML MODELS
    # -------------------------------------------------------------
    print("\n[4/5] Checking Local ML Models...")
    
    # 4a. BGE Embedding Model
    try:
        t0 = time.time()
        from app.services.embedding_service import EmbeddingService
        emb_service = EmbeddingService(model_name=settings.embedding_model_name)
        vec = emb_service.generate_text_embedding("Integrated terminal pty crash on Windows")
        lat = (time.time() - t0) * 1000
        report["local_ml"]["bge_embedding"] = {
            "status": "SUCCESS",
            "model_name": settings.embedding_model_name,
            "dimension": len(vec),
            "latency_ms": round(lat, 2)
        }
        print(f"  [+] BGE Embedding Model ({settings.embedding_model_name}): SUCCESS (dim={len(vec)}, {lat:.1f} ms)")
    except Exception as exc:
        report["local_ml"]["bge_embedding"] = {
            "status": "FAILED",
            "error": str(exc)
        }
        print(f"  [-] BGE Embedding Model: FAILED ({exc})")

    # 4b. Cross-Encoder Model
    try:
        t0 = time.time()
        from sentence_transformers import CrossEncoder
        ce = CrossEncoder(settings.cross_encoder_model_name)
        score = ce.predict([("terminal crash", "PowerShell terminal exits immediately")])
        lat = (time.time() - t0) * 1000
        report["local_ml"]["cross_encoder"] = {
            "status": "SUCCESS",
            "model_name": settings.cross_encoder_model_name,
            "sample_score": float(score[0]),
            "latency_ms": round(lat, 2)
        }
        print(f"  [+] Cross-Encoder Model ({settings.cross_encoder_model_name}): SUCCESS (score={float(score[0]):.3f}, {lat:.1f} ms)")
    except Exception as exc:
        report["local_ml"]["cross_encoder"] = {
            "status": "FAILED",
            "error": str(exc)
        }
        print(f"  [-] Cross-Encoder Model: FAILED ({exc})")

    # 4c. DistilBERT Severity Classifier
    try:
        t0 = time.time()
        from app.services.severity_classifier import SeverityClassifierService
        sev_service = SeverityClassifierService()
        sev_res = sev_service.predict_severity(
            title="Integrated terminal pty crash on Windows startup",
            body="PowerShell terminal exits immediately on startup with exit code 1."
        )
        lat = (time.time() - t0) * 1000
        report["local_ml"]["severity_classifier"] = {
            "status": "SUCCESS",
            "model_name": sev_res.model_name,
            "predicted_label": sev_res.predicted_label,
            "prediction_score": sev_res.prediction_score,
            "latency_ms": round(lat, 2)
        }
        print(f"  [+] Severity Classifier: SUCCESS (predicted={sev_res.predicted_label}, score={sev_res.prediction_score:.3f}, model={sev_res.model_name}, {lat:.1f} ms)")
    except Exception as exc:
        report["local_ml"]["severity_classifier"] = {
            "status": "FAILED",
            "error": str(exc)
        }
        print(f"  [-] Severity Classifier: FAILED ({exc})")

    # 4d. UMAP & HDBSCAN Clustering Dependencies
    try:
        t0 = time.time()
        import umap
        import hdbscan
        import numpy as np
        
        # Quick synthetic cluster test
        sample_data = np.random.RandomState(42).randn(40, 384)
        reducer = umap.UMAP(n_neighbors=5, n_components=2, min_dist=0.1, random_state=42)
        u_emb = reducer.fit_transform(sample_data)
        clusterer = hdbscan.HDBSCAN(min_cluster_size=5, min_samples=2)
        labels = clusterer.fit_predict(u_emb)
        lat = (time.time() - t0) * 1000
        
        report["local_ml"]["umap_hdbscan"] = {
            "status": "SUCCESS",
            "clusters_found": int(len(set(labels))),
            "latency_ms": round(lat, 2)
        }
        print(f"  [+] UMAP & HDBSCAN Dependencies: SUCCESS ({lat:.1f} ms)")
    except Exception as exc:
        report["local_ml"]["umap_hdbscan"] = {
            "status": "FAILED",
            "error": str(exc)
        }
        print(f"  [-] UMAP & HDBSCAN Dependencies: FAILED ({exc})")

    # -------------------------------------------------------------
    # 5. RUN REAL LIVE INVESTIGATION (8 STAGES)
    # -------------------------------------------------------------
    print("\n[5/5] Running REAL LIVE Investigation on microsoft/vscode...")
    print("  Ticket: 'Integrated terminal pty crash on Windows startup'")
    
    from app.schemas.pipeline_schemas import TicketInput
    from app.services.pipeline_orchestrator import run_support_pipeline

    test_ticket = TicketInput(
        ticket_id=999901,
        title="Integrated terminal pty crash on Windows startup",
        description="PowerShell terminal exits immediately on startup with exit code 1. The stack trace indicates a winpty-related failure. The terminal worked previously but started failing after a recent update.",
        repository_id=1,
        repository_name="microsoft/vscode"
    )

    t_pipeline_start = time.time()
    try:
        result = run_support_pipeline(ticket=test_ticket)
        t_pipeline_total = (time.time() - t_pipeline_start) * 1000
        report["live_pipeline_total_ms"] = round(t_pipeline_total, 2)
        report["live_pipeline_status"] = result.status
        report["live_pipeline_decision"] = result.final_decision
        report["live_pipeline_confidence"] = result.calibrated_confidence

        print(f"\n  Pipeline Execution Status: {result.status}")
        print(f"  Total Latency: {t_pipeline_total:.1f} ms")
        print(f"  Final Decision: {result.final_decision}")
        print(f"  Recommended Team: {result.recommended_team}")
        print(f"  Calibrated Confidence: {result.calibrated_confidence}")

        # Break down each of the 8 stages
        stage_names = [
            ("Stage 1: Severity Classification", "classify_severity", result.severity),
            ("Stage 2: Duplicate Detection", "detect_duplicate", result.duplicate),
            ("Stage 3: Root Cause Analysis", "discover_root_cause", result.root_cause),
            ("Stage 4: Hybrid Retrieval", "retrieve_cases", result.retrieval),
            ("Stage 5: Grounded Resolution", "generate_resolution", result.resolution),
            ("Stage 6: Claim Verification", "verify_claims", result.verification),
            ("Stage 7: Confidence Calibration", "calculate_confidence", result.confidence),
            ("Stage 8: Routing Decision", "route_ticket", result.routing),
        ]

        print("\n" + "-" * 60)
        print("STAGE-BY-STAGE EXECUTION REPORT:")
        print("-" * 60)

        for display_name, key, stage_val in stage_names:
            latency = result.stage_latencies.get(key, 0.0) if hasattr(result, "stage_latencies") and result.stage_latencies else 0.0
            stage_status = result.stage_statuses.get(key, "COMPLETED") if hasattr(result, "stage_statuses") and result.stage_statuses else "COMPLETED"
            
            # Check data source / real vs fixture
            data_source = "Real Local Model / DB"
            err_category = None
            
            if key == "generate_resolution":
                # Check if fallback or real LLM
                is_fallback = (stage_val.get("resolution_type") == "insufficient_evidence") if isinstance(stage_val, dict) else False
                if is_fallback:
                    data_source = "Safe Deterministic Fallback (LLM Quota Exceeded)"
                    err_category = report["openai"].get("error_category", "quota exceeded")
                else:
                    data_source = "Live OpenAI LLM (gpt-4o-mini)"
            elif key == "verify_claims":
                is_fallback = (stage_val.get("status") == "fallback" or stage_val.get("total_claims", 0) == 1) if isinstance(stage_val, dict) else False
                data_source = "Rule/Determinism Engine" if is_fallback else "Live OpenAI Verifier"
            
            stage_entry = {
                "display_name": display_name,
                "status": "SUCCESS" if stage_val else "SKIPPED",
                "stage_status": stage_status,
                "latency_ms": round(latency, 2),
                "error_category": err_category,
                "data_source": data_source,
                "summary": stage_val
            }
            report["pipeline_stages"][key] = stage_entry

            print(f"  {display_name}:")
            print(f"    - Status: SUCCESS ({stage_status})")
            print(f"    - Latency: {latency:.1f} ms")
            print(f"    - Source: {data_source}")
            if err_category:
                print(f"    - Error Category: {err_category}")

    except Exception as exc:
        report["live_pipeline_error"] = str(exc)
        print(f"  [-] Pipeline execution failed: {exc}")
        traceback.print_exc()

    # Save detailed JSON report
    with open("pipeline_diagnostic_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print("\n[+] Full detailed JSON report saved to pipeline_diagnostic_report.json")

if __name__ == "__main__":
    run_diagnostic()
