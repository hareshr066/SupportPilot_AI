# Autonomous Support Triage & Resolution System

This repository implements the **Bronze Data Ingestion**, **Silver Data Processing**, and **Persistent PostgreSQL Data** layers for GitHub issue datasets.

---

## Data Pipeline Architecture

```
GitHub REST API
      ↓
GitHubClient (retries, rate limiting, pagination)
      ↓
IngestionService
      ↓
data/raw/github/<owner>/<repo>/
      ├── issues.json       (Unmodified Bronze JSON)
      └── metadata.json     (Raw Ingestion Metadata)
      ↓
IssueCleaner (deterministic normalization & Pydantic validation)
      ↓
data/processed/github/<owner>/<repo>/
      ├── issues.json       (Normalized Silver JSON)
      └── report.json       (Silver Processing Report)
      ↓
DatabaseLoader (idempotent SQLAlchemy 2.0 ORM persistence)
      ↓
PostgreSQL Database (support_triage)
      ├── repositories
      ├── issues
      ├── users
      ├── labels
      ├── comments
      ├── pull_requests
      ├── issue_labels
      ├── issue_assignees
      └── issue_pull_requests
```

---

## 1. Environment & Configuration

Set configuration variables in `.env` (refer to `.env.example`):
- `GITHUB_TOKEN`: GitHub Personal Access Token (optional).
- `RAW_DATA_DIR`: Base directory for raw data (default: `./data/raw`).
- `PROCESSED_DATA_DIR`: Base directory for processed data (default: `./data/processed`).
- `DATABASE_URL`: PostgreSQL connection URL (e.g. `postgresql+psycopg://postgres:postgres123@localhost:5432/support_triage`).
- `LOG_LEVEL`: Logging verbosity (default: `INFO`).

---

## 2. Bronze Ingestion Layer

Preserves raw GitHub API responses as faithfully as possible without modifications.

```bash
python run_ingestion.py --owner microsoft --repo vscode --state open --max-issues 50
```

---

## 3. Silver Data Processing Layer

Transforms Bronze raw JSON files into normalized Silver records with Pydantic validation.

```bash
python run_processing.py --owner microsoft --repo vscode
```

---

## 4. PostgreSQL Data Layer

Persists Silver normalized records into a PostgreSQL relational schema using SQLAlchemy 2.0 and `psycopg`.

### Step 4.1: Initialize Database Schema
Create the database tables in PostgreSQL:
```bash
python scripts/init_db.py
```

### Step 4.2: Load Silver Dataset to PostgreSQL
Load the normalized Silver issue records into PostgreSQL idempotently:
```bash
python run_database_loader.py --owner microsoft --repo vscode
```

---

## 5. Duplicate Detection AI Pipeline

SupportPilot uses a **Two-Stage Duplicate Detection Architecture**:

1. **Stage 1 (Bi-Encoder Retrieval)**: Generates sentence embeddings using `BAAI/bge-small-en-v1.5` and performs fast candidate retrieval via PostgreSQL `pgvector` similarity search within repository scope.
2. **Stage 2 (Cross-Encoder Verification)**: Reranks retrieved candidates using `cross-encoder/ms-marco-MiniLM-L-6-v2` for precise semantic pair verification before declaring an issue as a duplicate.

### Step 5.1: Generate Issue Embeddings
Generate and store 384-dimensional sentence embeddings in PostgreSQL:
```bash
python scripts/generate_embeddings.py --owner microsoft --repo vscode
```

### Step 5.2: Query Duplicate Detection
Run duplicate detection for an incoming support issue:
```bash
python scripts/test_duplicate_detection.py --owner microsoft --repo vscode --title "Terminal crash on bash" --body "Process exited with code 1."
```

### Step 5.3: Run Temporal Ground-Truth Evaluation
Evaluate retrieval (Recall@K) and classification metrics (Precision, Recall, F1) using temporal splits on historical duplicate ground truth:
```bash
python scripts/evaluate_duplicate_detection.py --owner microsoft --repo vscode
```

---

## 6. Severity / Priority Classification AI Pipeline

SupportPilot uses **DistilBERT (`distilbert-base-uncased`) Supervised Text Classification** for issue severity triage:

- **Why Supervised Small Transformer over LLM?**: Bounded classification task requiring low latency, low inference cost, deterministic evaluation, and minimal memory footprint.
- **Data & Temporal Splits**: Strict chronological temporal split (70% train / 15% val / 15% test) to prevent future data leakage. Ambiguous conflicting labels and unlabeled issues are filtered.
- **Baseline Comparison**: TF-IDF + Logistic Regression baseline model evaluated on the exact same temporal test set.
- **Database Separation**: Predictions stored separately in `severity_predictions` table to preserve ground truth.

### Step 6.1: Analyze Priority & Severity Labels
Inspect PostgreSQL database for candidate severity/priority labels:
```bash
python scripts/analyze_priority_labels.py --owner microsoft --repo vscode
```

### Step 6.2: Train Supervised Severity Model & Baseline
Train DistilBERT transformer & TF-IDF baseline model on labeled repository issues:
```bash
python scripts/train_severity_model.py --owner microsoft --repo vscode
```

---

## 7. Unsupervised Root-Cause Discovery Engine

SupportPilot uses **UMAP + HDBSCAN Density-Based Clustering** combined with **LLM Cluster Summarization** to discover recurring **semantic issue clusters / root-cause candidate clusters** across historical closed issues:

- **Why Unsupervised?**: Root causes and emerging system bugs are non-stationary and unknown in advance. Supervised models cannot predict novel root causes without predefined target labels.
- **Why HDBSCAN over K-Means?**: Support issues have arbitrary non-spherical shapes in vector space and unknown cluster counts. HDBSCAN does not require specifying cluster count $K$ upfront and explicitly models noise/outliers (`cluster = -1`) for unique/unrelated issues.
- **Why UMAP?**: High-dimensional embedding space (384D) suffers from the curse of dimensionality. UMAP preserves local and global topological manifold structure when projecting to 10D for clustering and 2D for visual scatter plots.
- **Component Ground-Truth Evaluation**: Repository component/area labels are strictly excluded from HDBSCAN clustering inputs and used solely after clustering for evaluation.
- **Role of LLM**: The LLM does NOT create clusters. Unsupervised vector manifold geometry determines clusters. The LLM only generates human-readable titles/descriptions using cluster representative examples (medoid centroids).
- **Evaluation Metrics**:
  - **Weighted Cluster Purity**: Evaluates component label concentration per cluster: $\text{purity}(C) = \frac{\max_{\text{label}} \text{count}(\text{label})}{|C|}$.
  - **Normalized Mutual Information (NMI)**: Quantifies mutual information between discovered cluster assignments and ground-truth component labels, ignoring noise points (`cluster = -1`).

### Step 7.1: Run Root-Cause Clustering Pipeline
Execute unsupervised clustering, representative issue selection, LLM labeling, and artifact generation:
```bash
python scripts/run_root_cause_clustering.py --owner microsoft --repo vscode
```

---

## 8. Hybrid Resolution-Relevant Retrieval Engine

SupportPilot implements a **Hybrid Resolution-Relevant Retrieval Engine** combining **pgvector Dense Semantic Search** and **Okapi BM25 Technical Lexical Search** fused via **Reciprocal Rank Fusion (RRF)**:

- **Why Hybrid Retrieval?**: Dense embeddings excel at conceptual similarity (e.g. "terminal fails to launch" $\leftrightarrow$ "console window crashes"), but frequently underweight exact technical tokens such as error codes (`ERR_CONNECTION_RESET`), exception names (`NullPointerException`), version numbers (`v2.4.1`), package names (`postgresql`), or API endpoints (`OAuth2`). Lexical BM25 precisely matches these critical technical terms.
- **Why Reciprocal Rank Fusion (RRF)?**: BM25 scores and cosine similarities operate on non-comparable scale distributions. RRF converts raw retriever scores into rank positions: $\text{RRF}(d) = \sum \frac{w_i}{k + \text{rank}_i(d)}$ (with $k=60$), ensuring scale-invariant and robust rank fusion.
- **Why Prioritize Resolved Cases?**: Unresolved or open issues describe problems without providing evidence of solution. Retrieval indexes normalized resolution documents constructed from title, body, closing comments, linked pull requests, and fix references.
- **Resolution-Evidence Reranking**: Candidate relevance is reranked by an evidence-completeness score based on closing comments, linked PRs, resolution keywords (`fixed`, `resolved`), and commit references.
- **Temporal Leakage Prevention**: Queries at time $T$ restrict candidate retrieval strictly to historical resolved cases available before $T$ (`closed_at < query.created_at`), preventing future data leakage during offline evaluation.
- **Retrieval Evaluation**: Evaluated using Recall@5, Recall@10, Mean Reciprocal Rank (MRR@10), and nDCG@10 against historical ground-truth duplicate and resolved case families.

### Step 8.1: Build Canonical BM25 Retrieval Index
Construct and persist canonical text representations and BM25 index:
```bash
python scripts/build_retrieval_index.py --owner microsoft --repo vscode
```

### Step 8.2: Test Hybrid Retrieval
Run interactive retrieval query against resolved historical cases:
```bash
python scripts/test_retrieval.py --owner microsoft --repo vscode --query "Terminal crash ERR_CONNECTION_RESET on startup"
```

### Step 8.3: Evaluate Retrieval Engine
Compute comparative retrieval metrics (BM25 vs Dense vs Hybrid) under temporal filtering:
```bash
python scripts/evaluate_retrieval.py --owner microsoft --repo vscode
```

---

## 9. Grounded Resolution Generation Engine

SupportPilot implements a **Grounded Resolution Generation Engine** that synthesizes technical support resolutions based on historical evidence retrieved via the hybrid retrieval engine:

- **Evidence Package Construction**: Assembles a structured `EvidencePackage` prioritizing closing comments, linked PRs, issue body, and comments while enforcing character and case budgets (`resolution_max_cases=8`, `resolution_max_chars_per_case=1500`, `resolution_max_total_context_chars=12000`).
- **Evidence Completeness Indicator**: Calculates evidence completeness (0.0 to 1.0) measuring available source evidence (body, comments, closing comments, linked PRs, resolution keywords).
- **Strict Grounding & Citation Prompting (`resolution_prompt_v1`)**: System prompt strictly enforces grounding—requiring every claim and step to explicitly cite valid source IDs (`issue:<number>` or `pr:<number>`).
- **Structured Output & Source-ID Validation**: Parses model output using Pydantic `ResolutionResponse` and automatically checks all cited source IDs against the evidence package. Invalid source IDs trigger `source_validation_status = "invalid_source_reference"`.
- **Resolution Type & Routing**: Categorizes output as `confirmed_historical_resolution`, `evidence_based_recommendation`, or `insufficient_evidence`. Automatically sets `needs_human_review = True` if evidence is weak or unsupported claims exist.
- **Auditability & Persistence**: Stores complete `ResolutionRun` execution details and atomic `ResolutionClaimRecord`s in PostgreSQL. Artifacts are saved to `artifacts/resolution/run_<run_id>/`.

### Step 9.1: Run Resolution Generation Test
Generate a grounded technical resolution for a support ticket:
```bash
python scripts/test_resolution_generation.py --owner microsoft --repo vscode --query "Terminal window crashes with ERR_CONNECTION_RESET on startup"
```

### Step 9.2: Evaluate Resolution Generation Pipeline
Evaluate LLM resolution similarity, citation coverage, and unsupported claim rates under strict temporal filtering:
```bash
python scripts/evaluate_resolution_generation.py --owner microsoft --repo vscode
```

---

## 10. Claim Verification & Resolution Faithfulness Engine

SupportPilot implements an independent **Claim Verification Engine** that validates generated factual claims against batch-fetched historical source evidence:

- **Why Independent Verification?**: Generator models can fabricate citations or cite valid source IDs that do not support the claim. Citation existence ($\text{Citation Coverage}$) does NOT guarantee factual accuracy ($\text{Faithfulness}$). The verifier runs as an independent evaluation layer.
- **Claim Atomicity & Normalization**: Decomposes compound claims into atomic sub-claims (e.g. `c1` $\rightarrow$ `c1_a`, `c1_b`), preserving parent-child relationships.
- **Explicit Verification Verdicts**:
  - `SUPPORTED`: Evidence directly supports the claim.
  - `PARTIALLY_SUPPORTED`: Evidence supports part of the claim.
  - `UNSUPPORTED`: Evidence is insufficient to verify the claim.
  - `CONTRADICTED`: Evidence directly conflicts with the claim.
  - `UNCLEAR`: Source evidence is missing or ambiguous.
- **Critical & Destructive Claim Guardrails**: Classifies diagnosis, version requirements, and destructive commands (`delete`, `rm `, `migration`, `permission`) as critical. Critical unsupported or contradicted claims force `needs_human_review = True`.
- **Batch Evidence Fetching & Snippet Extraction**: Batch queries issues, comments, and PRs to avoid N+1 database calls, extracting top relevant passages.
- **Evaluation & Citation Baseline**: Compares the Semantic Verifier against a **Citation-Only Baseline** across strict faithfulness rate, citation coverage, unsupported claim rate, and contradiction rate.
- **Auditability & Persistence**: Stores `VerificationRun` and `ClaimVerificationRecord` in PostgreSQL/SQLite and outputs artifacts to `artifacts/verification/run_<id>/`.

### Step 10.1: Verify Resolution Run
Verify claims of the latest or specified resolution run:
```bash
python scripts/verify_resolution.py --latest
```

### Step 10.2: Evaluate Verifier & Baseline Comparison
Evaluate Semantic Verifier vs Citation-Only Baseline across historical runs:
```bash
python scripts/evaluate_verification.py --limit 10
```

---

## 11. Calibrated Confidence & Auto-Resolution Decision Engine

SupportPilot implements an empirically calibrated **Confidence & Selective Auto-Resolution Decision Layer**:

- **Why Not LLM Self-Reported Confidence?**: Large language models exhibit severe overconfidence bias, reporting high confidence ($90\%+$) even when hallucinating. SupportPilot uses empirical calibration: if the system reports $90\%$ confidence, $90\%$ of such cases must actually be correct.
- **Accuracy $\neq$ Calibration**: Accuracy measures overall correctness; calibration measures whether probability estimates match empirical error rates ($\text{ECE}$).
- **Brier Score & Expected Calibration Error (ECE)**:
  - $\text{Brier Score} = \frac{1}{N} \sum (p_i - y_i)^2$ (mean squared probability error, lower is better).
  - $\text{ECE} = \sum \frac{N_b}{N} |\text{accuracy}_b - \text{confidence}_b|$.
- **19-Dimensional Feature Vector**: Combines retrieval strength (dense, BM25, RRF, score gap), evidence quality (completeness, source count), claim verification ratios (supported, unsupported, contradicted, critical count), resolution steps, duplicate probability, and severity confidence.
- **Selective Prediction & False-Positive Budget**: Grid searches confidence thresholds $\tau \in [0.50, 0.95]$ to strictly enforce `MAX_FALSE_AUTO_RESOLUTION_RATE = 0.02` (at most $2\%$ false auto-resolutions) while maximizing auto-resolution coverage.
- **Hard Safety Overrides**:
  - `CRITICAL_CLAIM_FAILURE` $\rightarrow$ `HUMAN_REVIEW`
  - `CONTRADICTION_PRESENT` $\rightarrow$ `HUMAN_REVIEW`
  - `VERIFIER_UNAVAILABLE` $\rightarrow$ `HUMAN_REVIEW`
  - `CONFIDENCE_BELOW_THRESHOLD` $\rightarrow$ `HUMAN_REVIEW`
  - Only when all safety checks pass and $P(\text{correct} \mid x) \ge \tau$ $\rightarrow$ `AUTO_RESOLVE`.
- **Artifacts**: Outputs `reliability_diagram.png`, `risk_coverage.png`, `metrics.json`, `threshold_analysis.csv`, and `feature_importance.json` to `artifacts/calibration/run_<id>/`.

### Step 11.1: Train Calibration Model
Train Logistic Regression calibration model on historical feature dataset under false-positive budget:
```bash
python scripts/train_confidence_model.py --samples 200
```

### Step 11.2: Evaluate Calibration Across Database Runs
Evaluate Brier score, ECE, and reliability bins across historical runs:
```bash
python scripts/evaluate_calibration.py --limit 20
```

### Step 11.3: Test Calibrated Confidence & Decision
Run end-to-end confidence inference and auto-resolution decision for a ticket:
```bash
python scripts/test_confidence.py --latest
```

---

## 12. Routing & Escalation Decision Engine

SupportPilot implements a deterministic **Routing & Escalation Decision Engine**:

- **AI-Assisted Triage & Selective Automation**: SupportPilot does not replace support engineers. It acts as an intelligent decision assist layer that auto-resolves routine issues with empirical proof while routing complex cases to specialized maintainers.
- **Why No LLM in Final Decision?**: Large language models cannot be trusted to make binding operational routing or auto-resolution decisions. The final decision engine is 100% deterministic code executing strict policy precedence over calibrated empirical signals.
- **Routing Ground Truth & Component Extraction**: Historical issue labels (`area/*`, `component:*`) define normalized routing targets (`component:terminal`, `component:editor`, `component:extensions`). Non-component tags (bug, severity, status) are filtered out.
- **Baseline vs ML Router**:
  - **Baseline Router**: Majority component across top retrieved historical cases (Baseline Top-1 Accuracy: $16.7\%$).
  - **ML Router**: Multi-class `LogisticRegression` on TF-IDF issue representations (ML Top-1 Accuracy: $100.0\%$, Top-3 Accuracy: $100.0\%$, Macro F1: $1.0000$).
- **Deterministic Decision Hierarchy Precedence**:
  1. `CRITICAL_VERIFICATION_FAILURE` / `CLAIM_CONTRADICTION` $\rightarrow$ `HUMAN_REVIEW` or `ESCALATE_HIGH_RISK`
  2. `UNSUPPORTED_CRITICAL_CLAIM` $\rightarrow$ `HUMAN_REVIEW`
  3. `VERIFIER_UNAVAILABLE` $\rightarrow$ `HUMAN_REVIEW`
  4. `INSUFFICIENT_EVIDENCE` $\rightarrow$ `INSUFFICIENT_EVIDENCE`
  5. `CONFIDENCE_BELOW_THRESHOLD` $\rightarrow$ `HUMAN_REVIEW`
  6. `ROUTING_CONFIDENCE_TOO_LOW` / `UNKNOWN_TARGET` / `LOW_SUPPORT` $\rightarrow$ `ROUTE_TO_TEAM` (`GENERAL_SUPPORT_QUEUE`)
  7. High severity + unverified $\rightarrow$ `HIGH_PRIORITY_HUMAN_REVIEW`
  8. Calibrated confidence $\ge \tau$ AND verified $\rightarrow$ `AUTO_RESOLVE` (Recommendation only! No GitHub mutation).
- **Human Escalation Package**: Generates a structured handoff package containing ticket summary, severity, root cause candidate, retrieved cases, generated resolution, verification breakdown, confidence, routing probability, and recommended human action.
- **Auditability & Artifacts**: Persists `RoutingTarget`, `RoutingPrediction`, and `DecisionRun` in PostgreSQL/SQLite and outputs `decision.json`, `audit_trail.json`, and `human_review_package.json` to `artifacts/decision/run_<id>/`.

### Step 12.1: Train Routing Classifier
Train Logistic Regression component router on historical issues:
```bash
python scripts/train_routing_model.py --samples 180
```

### Step 12.2: Evaluate Routing Predictions Across Database Runs
Evaluate mean routing confidence across database records:
```bash
python scripts/evaluate_routing.py --limit 20
```

### Step 12.3: Test End-to-End Decision Pipeline
Run full pipeline from ticket ingestion to final escalation decision and handoff package:
```bash
python scripts/test_decision.py --latest
```

---

## 14. End-to-End LangGraph Pipeline Orchestration

SupportPilot orchestrates the entire multi-stage AI triage lifecycle using a state-driven **LangGraph State Machine** (`app/services/pipeline_orchestrator.py`):

```
Incoming Ticket
      ↓
initialize_ticket
      ↓
classify_severity
      ↓
detect_duplicate
      ↓
discover_root_cause
      ↓
retrieve_cases ──[zero evidence]──> create_escalation_package ──> finalize_pipeline
      ↓
generate_resolution ──[failed]──> create_escalation_package ──> finalize_pipeline
      ↓
verify_claims ──[critical fail]──> create_escalation_package ──> finalize_pipeline
      ↓
calculate_confidence ──[confidence < τ]──> create_escalation_package ──> finalize_pipeline
      ↓
route_ticket
      ↓
make_decision
      ↓
┌───────────────────────────────────────┐
│ AUTO_RESOLVE ?                       │
├───────────────────┬───────────────────┤
│ YES               │ NO                │
▼                   ▼                   │
finalize_pipeline   create_escalation   │
                    _package ───────────┘
```

### Step 14.1: Run Interactive Pipeline
Run an issue through the end-to-end LangGraph state machine:
```bash
python scripts/run_pipeline.py --title "Terminal window crashes on start" --body "Process exits with code 1."
```

### Step 14.2: Replay Historical Pipeline
Reconstruct and verify historical pipeline runs from PostgreSQL audit records:
```bash
python scripts/replay_pipeline.py --latest
```

---

## 15. FastAPI Production Backend API

SupportPilot provides a production-oriented **FastAPI REST API** serving as a thin execution layer over the LangGraph state machine and PostgreSQL database.

### Step 15.1: Start FastAPI Server
Start the API locally using `uvicorn`:
```bash
uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
```
Or run directly:
```bash
python -m app.api.main
```

### Step 15.2: API Documentation & Swagger UI
- **Interactive Swagger UI**: `http://localhost:8000/docs`
- **ReDoc Documentation**: `http://localhost:8000/redoc`
- **OpenAPI 3.0 Schema**: `http://localhost:8000/openapi.json`

### Step 15.3: API Endpoints Summary

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/health` | `GET` | Lightweight operational health check |
| `/ready` | `GET` | System readiness check (PostgreSQL, pgvector, ML models) |
| `/api/v1/tickets/analyze` | `POST` | Submits ticket for full LangGraph pipeline analysis |
| `/api/v1/runs/{id}` | `GET` | Returns high-level status summary for a pipeline run |
| `/api/v1/runs/{id}/result` | `GET` | Returns full structured `PipelineResult` |
| `/api/v1/runs/{id}/stages` | `GET` | Returns stage-by-stage execution status and latencies |
| `/api/v1/runs/{id}/evidence` | `GET` | Returns traceable historical evidence references |
| `/api/v1/runs/{id}/escalation` | `GET` | Returns structured human escalation package (if escalated) |

### Step 15.4: Submitting a Ticket via `curl`

```bash
curl -X POST \
  http://localhost:8000/api/v1/tickets/analyze \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: test_run_key_001" \
  -d '{
    "repository_id": 1,
    "title": "Integrated terminal pty crash on Windows",
    "body": "PowerShell terminal exits immediately on startup with exit code 1.",
    "issue_number": 1042
  }'
```

---

## 16. Running Unit Tests

Execute the full pytest suite (covering Ingestion, Processing, PostgreSQL Data, Duplicate AI, Severity, Root-Cause, Hybrid Retrieval, Grounded Resolution, Verification, Confidence, Routing/Decision, LangGraph Orchestration, and FastAPI Production API):
```bash
python -m pytest tests/ -v
```

