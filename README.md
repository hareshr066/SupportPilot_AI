<div align="center">

# ✈️ SupportPilot AI
### **Autonomous Support Triage & Grounded Resolution Engine**

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://fastapi.tiangolo.com)](https://reactjs.org)
[![Vite](https://img.shields.io/badge/Vite-5.0+-646CFF.svg?style=for-the-badge&logo=vite&logoColor=white)](https://vitejs.dev)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16.0+-4169E1.svg?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-Orchestration-FF6B6B.svg?style=for-the-badge)](https://www.langchain.com/langgraph)
[![Pytest](https://img.shields.io/badge/Pytest-145%2F145%20Passed-brightgreen.svg?style=for-the-badge&logo=pytest&logoColor=white)](https://pytest.org)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.13-3776AB.svg?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org)

*Zero-touch support engineering, automated incident triage, grounded root-cause correlation, claim verification, and calibrated auto-resolution.*

---

</div>

## 📌 Executive Summary

**SupportPilot AI** is an enterprise-grade, state-driven autonomous support triage and resolution engine. Built on a modular **LangGraph** orchestration graph, SupportPilot automates support ticket ingestion, duplicate issue detection, severity classification, root-cause correlation, evidence-grounded resolution generation, claim verification, and calibrated confidence routing.

SupportPilot features a **WebGL-powered Mission Control Dashboard** for real-time telemetry and a server-to-server **External Integration REST API** (`/v1/tickets`) designed for seamless connection with production web applications (e.g. StudySync).

---

## 🏗️ End-to-End System Architecture

```
                                    EXTERNAL CLIENTS & WEBHOOKS
                                (StudySync API / GitHub Webhooks)
                                                │
                                                ▼
                                    [ FastAPI Gateway & Auth ]
                                  (SUPPORTPILOT_API_KEY / CORS)
                                                │
                                                ▼
                             ┌─────────────────────────────────────┐
                             │  LangGraph State Orchestrator Graph │
                             └─────────────────────────────────────┘
                                                │
         ┌─────────────────────────┬────────────┴────────────┬─────────────────────────┐
         ▼                         ▼                         ▼                         ▼
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│Duplicate Detector│       │Severity Classifier│     │Root-Cause Engine│       │Hybrid Retriever │
│ Bi/Cross-Encoder│       │  Fine-Tuned     │       │  UMAP + HDBSCAN │       │ Dense BGE + BM25│
│  BGE + pgvector │       │   DistilBERT    │       │  Cluster Medoid │       │ RRF Fusion      │
└────────┬────────┘       └────────┬────────┘       └────────┬────────┘       └────────┬────────┘
         │                         │                         │                         │
         └─────────────────────────┼─────────────────────────┴─────────────────────────┘
                                   │
                                   ▼
                       ┌──────────────────────┐
                       │ Resolution Generator │
                       │ GPT-4o / Safe Fallback│
                       └───────────┬──────────┘
                                   │
                                   ▼
                       ┌──────────────────────┐
                       │  Claim Verifier      │
                       │ Faithfulness Check   │
                       └───────────┬──────────┘
                                   │
                                   ▼
                       ┌──────────────────────┐
                       │Confidence Calibrator │
                       │Isotonic / ECE Budget │
                       └───────────┬──────────┘
                                   │
                                   ▼
                       ┌──────────────────────┐
                       │ Routing & Decision   │
                       │ AUTO-RESOLVE vs      │
                       │ HUMAN-ESCALATION     │
                       └──────────────────────┘
```

---

## 🌟 Key Features & AI Infrastructure

### 1. 🔄 Two-Stage Semantic Duplicate Detection
* **Stage 1 (Bi-Encoder Candidate Retrieval)**: Generates 384-dimensional sentence embeddings using `BAAI/bge-small-en-v1.5` and performs fast $K$-NN vector similarity search via PostgreSQL `pgvector`.
* **Stage 2 (Cross-Encoder Verification)**: Reranks candidate pairs using `cross-encoder/ms-marco-MiniLM-L-6-v2` for precise semantic pair verification before declaring an issue as a duplicate.

### 2. ⚡ Fine-Tuned Supervised Severity Classification
* Uses a fine-tuned small Transformer (`distilbert-base-uncased`) for low-latency, deterministic severity triage (`CRITICAL`, `HIGH`, `NORMAL`, `LOW`).
* Evaluated against a TF-IDF + Logistic Regression baseline using strict chronological temporal splits to prevent data leakage.

### 3. 🧬 Unsupervised Root-Cause Discovery Engine
* **UMAP + HDBSCAN Density Clustering**: Discovers emerging, non-stationary system bug clusters across historical closed issues without requiring predefined labels.
* **Cluster Medoids**: Identifies representative centroid medoids for LLM cluster title/description summarization while preserving underlying manifold geometry.

### 4. 🔎 Hybrid Resolution Retrieval (Dense + Sparse RRF)
* Fuses **Dense Semantic Vectors** (`bge-small-en-v1.5`) and **Sparse Technical Keyphrase Indexing** (BM25 tokenized) using **Reciprocal Rank Fusion (RRF)** ($k=60$) to fetch resolution-relevant historical cases.

### 5. 🛡️ Grounded Resolution & Claim Verification
* Decomposes LLM-generated resolutions into individual verifiable technical claims.
* Verifies each claim against historical code snippets and issue comments, calculating evidence completeness scores ($0.0 - 1.0$) and preventing LLM hallucinations.

### 6. 📊 Calibrated Confidence & Decision Engine
* Employs **Isotonic Regression & Expected Calibration Error (ECE)** to enforce strict false-auto-resolution budgets ($\le 2\%$).
* Automatically routes low-confidence or contradicted tickets to `HUMAN_ESCALATION` queues while granting `AUTO_RESOLVE_RECOMMENDATION` for high-confidence tickets.

### 7. 🔌 External Ticket API (`/v1/tickets`) & Hardened Security
* Server-to-server API designed for production application integrations (e.g. StudySync).
* Protected by `SUPPORTPILOT_API_KEY` (`Authorization: Bearer <key>` or `X-API-Key: <key>`).
* Operates 100% reliably even when external LLM quotas are exhausted via structured safe degradation fallbacks.

### 8. 🎨 Modern WebGL Mission Control UI
* Built with **React 18**, **Vite**, and **Vanilla CSS / Glassmorphism**.
* Features an interactive **WebGL Cloud Shader Sky Horizon**, hardware-accelerated dynamic flight deck aircraft telemetry, real-time stage progress indicators, evidence inspectors, and interactive evaluation metrics.

---

## 🗄️ Database Architecture & Storage Layers

SupportPilot organizes data into three distinct pipeline stages:

| Layer | Component | Description |
| :--- | :--- | :--- |
| **Bronze** | Ingestion Service | Raw GitHub REST API JSON payloads stored as unmodified historical audit trails (`data/raw/`). |
| **Silver** | Processing Engine | Deterministically normalized, cleaned, and Pydantic-validated issue records (`data/processed/`). |
| **Gold** | PostgreSQL + pgvector | Production relational storage with vector embeddings, relational labels, comments, pull requests, and pipeline audit runs. |

### PostgreSQL Schema Entity Relationship

* `repositories`: Multi-repo registry and synchronization tracking.
* `issues`: Primary ticket records with state, title, body, and HTML URLs.
* `users`: GitHub authors, assignees, and comment contributors.
* `labels` & `comments` & `pull_requests`: Normalized metadata and historical context.
* `issue_embeddings`: 384D `pgvector` embeddings indexed with HNSW cosine distance.
* `severity_predictions`: Historical severity predictions separated from ground truth.
* `pipeline_runs` & `pipeline_stage_runs`: Stage-by-stage latency and decision audit logs.

---

## 🚀 Quickstart & Setup Guide

### 1. Prerequisites
* **Python**: `3.11` or `3.13`
* **Node.js**: `18.0+`
* **PostgreSQL**: `16.0+` (with `pgvector` extension)

### 2. Environment Configuration
Clone the repository and create your local `.env` file:
```bash
git clone https://github.com/hareshr066/SupportPilot_AI.git
cd SupportPilot_AI
cp .env.example .env
```

Configure your environment variables in `.env`:
```ini
APP_ENV=production
DATABASE_URL=postgresql+psycopg://postgres:postgres123@localhost:5432/support_triage
SUPPORTPILOT_API_KEY=your_secure_backend_api_key
OPENAI_API_KEY=your_openai_api_key_here
```

### 3. Install Backend Dependencies
```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 4. Initialize Database Schema
```bash
python scripts/init_db.py
```

### 5. Start Backend FastAPI Server
```bash
python -m app.api.main
```
The API server will start on `http://127.0.0.1:8000` (Swagger docs available at `/docs`).

### 6. Start Frontend React Application
```bash
cd frontend
npm install
npm run dev
```
The React Mission Control Dashboard will start on `http://localhost:5173`.

---

## 🧪 Running Automated Tests

SupportPilot includes a comprehensive Pytest suite covering unit, integration, pipeline orchestration, and external API contract tests:

```bash
# Run full backend test suite (145 tests)
python -m pytest -v --tb=short
```

To run frontend production compilation and type checks:
```bash
cd frontend
npm run build
```

---

## 🔌 External Ticket API Contract (`/v1/tickets`)

SupportPilot exposes a server-to-server REST API for external applications (e.g. StudySync):

### Create Ticket
```http
POST /v1/tickets
X-API-Key: your_supportpilot_api_key
Content-Type: application/json

{
  "title": "Study progress resets after refresh",
  "description": "After reviewing flashcards, today's study progress disappears after refreshing the application.",
  "application": "StudySync",
  "environment": "production",
  "feature": "study-progress"
}
```

**Response (`201 Created`)**:
```json
{
  "ticket_id": "SP-1042",
  "status": "RECEIVED",
  "application": "StudySync",
  "title": "Study progress resets after refresh",
  "description": "After reviewing flashcards, today's study progress disappears after refreshing the application.",
  "created_at": "2026-09-18T10:30:05.540621+05:30"
}
```

### Trigger Ticket Analysis
```http
POST /v1/tickets/SP-1042/analyze
X-API-Key: your_supportpilot_api_key
```

### Get Ticket Detail
```http
GET /v1/tickets/SP-1042
X-API-Key: your_supportpilot_api_key
```

### Get Pipeline Execution Status
```http
GET /v1/runs/{pipeline_run_id}
X-API-Key: your_supportpilot_api_key
```

---

## 📄 License & Attribution

Developed with ❤️ as part of the **SupportPilot AI Operations Platform**.
Built with FastAPI, React, Vite, SQLAlchemy 2.0, PyTorch, Hugging Face Transformers, UMAP, HDBSCAN, and LangGraph.
